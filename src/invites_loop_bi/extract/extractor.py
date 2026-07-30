"""
Config driven extraction engine.

Everything the engine needs is declared in `invites_loop_bi.config`; adding a
table to a pipeline never requires new code here.  Two load strategies exist:

* `IncrementalExtractor` -- watermark based.  The **first** run for a table has
	no watermark yet, so the whole table is read.  Every run after that only reads
	the rows whose watermark column moved past the last committed watermark, i.e.
	rows that were created or updated since then.
* `FullRefreshExtractor` -- the reference / meta tables listed in the
	`*_FULL_REFRESH_TARGETS` config lists.  Always read in full; the loader
	truncates and reloads the staging table.

Rows never become Python objects.  A run streams
`COPY (SELECT ...) TO STDOUT (FORMAT csv)` into a spooled buffer, and the staging
loader streams that buffer straight into the warehouse with `COPY ... FROM STDIN`.
Values therefore keep PostgreSQL's own text representation end to end -- no type
inference, nothing to lose on `jsonb`, arrays, enums or `numeric` -- and the copy
runs far faster than row-wise inserts.

Usage from a DAG / the pipeline:

	extractors = build_extractors(source_conn, meta_conn, "iccoli")
	for extractor in extractors:
		with extractor.extract() as result:      # reads the source
			stats = loader.load(result)           # writes staging
		extractor.commit(result, stats.observed_watermark, stats.rows_loaded)
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import IO, Any

from invites_loop_bi.config import (
	LOAD_TYPE_FULL_REFRESH,
	LOAD_TYPE_INCREMENTAL,
	get_extraction_targets,
)
from invites_loop_bi.extract.introspect import TableSchema, describe_table, quote_ident
from invites_loop_bi.extract.watermark import WatermarkManager

logger = logging.getLogger(__name__)

#: Extracted CSV is kept in memory up to this size, then spills to a temp file.
DEFAULT_SPOOL_MAX_BYTES = 128 * 1024 * 1024

#: Chunk size psycopg2 uses while shovelling COPY data.
COPY_BUFFER_SIZE = 1024 * 1024


@dataclass(frozen=True)
class ExtractionPlan:
	"""The query a single extraction run is about to copy out, plus its bounds."""

	source_system: str
	schema_name: str
	table_name: str
	load_type: str
	#: Column list / primary key of the source table, read from its catalog.
	source_table: TableSchema
	query: str
	params: tuple[Any, ...]
	#: The WHERE body of `query` (without the keyword), or None for a full read.
	#: The loader replays it against staging to delete exactly the window it is
	#: about to insert, which is how a table without a primary key stays
	#: idempotent. Takes the same `params`.
	predicate: str | None
	#: SQL expression the watermark is read from, e.g.
	#: `COALESCE("update_datetime", "create_datetime")`. None for full refresh.
	watermark_expr: str | None
	#: Last committed watermark; None on a full load (first run / full refresh).
	watermark_from: datetime | None
	upper_bound: datetime | None = None

	@property
	def label(self) -> str:
		return f"{self.source_system}.{self.schema_name}.{self.table_name}"

	@property
	def is_full_load(self) -> bool:
		"""True when the whole table is being read (first run or full refresh)."""
		return self.watermark_from is None


@dataclass
class ExtractionResult:
	"""
	What a run produced: a rewound CSV buffer ready to be copied into the DW.

	Close it (or use it as a context manager) to release the spool file.
	"""

	plan: ExtractionPlan
	csv: IO[bytes]
	row_count: int
	byte_count: int
	extracted_at: datetime

	@property
	def source_table(self) -> TableSchema:
		return self.plan.source_table

	@property
	def source_system(self) -> str:
		return self.plan.source_system

	@property
	def schema_name(self) -> str:
		return self.plan.schema_name

	@property
	def table_name(self) -> str:
		return self.plan.table_name

	@property
	def load_type(self) -> str:
		return self.plan.load_type

	@property
	def is_empty(self) -> bool:
		return self.row_count == 0

	def close(self) -> None:
		self.csv.close()

	def __enter__(self) -> ExtractionResult:
		return self

	def __exit__(self, *exc_info) -> bool:
		self.close()
		return False


class BaseExtractor:
	"""
	Shared machinery for every load strategy: catalog introspection, the COPY out,
	and watermark bookkeeping in the DW.

	The source connection must **not** be in autocommit mode: the catalog reads,
	the timestamp reading and the COPY all have to see one consistent snapshot.
	"""

	load_type: str = LOAD_TYPE_INCREMENTAL

	def __init__(
		self,
		source_conn,
		meta_conn=None,
		source_system: str = "",
		schema_name: str = "",
		table_name: str = "",
		*,
		exclude_columns: tuple[str, ...] = (),
		spool_max_bytes: int = DEFAULT_SPOOL_MAX_BYTES,
		watermark_manager: WatermarkManager | None = None,
	):
		# 1. Source DB connection for data extraction (Read-Only)
		self.source_conn = source_conn
		self.source_system = source_system
		self.schema_name = schema_name
		self.table_name = table_name
		#: Columns never read from the source (huge payloads the warehouse does not need).
		self.exclude_columns = tuple(exclude_columns)
		self.spool_max_bytes = spool_max_bytes

		# 2. Meta/DW DB connection for watermark management (Read-Write)
		if watermark_manager is None:
			if meta_conn is None:
				raise ValueError("Either `meta_conn` or `watermark_manager` must be provided")
			watermark_manager = WatermarkManager(meta_db_conn=meta_conn)
		self.wm_manager = watermark_manager

		self._source_table: TableSchema | None = None

	# ------------------------------------------------------------------ helpers

	@property
	def qualified_name(self) -> str:
		return f"{quote_ident(self.schema_name)}.{quote_ident(self.table_name)}"

	@property
	def label(self) -> str:
		return f"{self.source_system}.{self.schema_name}.{self.table_name}"

	def describe(self, refresh: bool = False) -> TableSchema:
		"""
		Columns and primary key of the source table (read once, then cached).

		Excluded columns are dropped here, so everything downstream -- the SELECT,
		the staging DDL, the merge -- simply never sees them.
		"""
		if self._source_table is None or refresh:
			schema = describe_table(self.source_conn, self.schema_name, self.table_name)
			if self.exclude_columns:
				logger.info("[%s] not extracting column(s): %s", self.label, ", ".join(self.exclude_columns))
				schema = schema.without(self.exclude_columns)
			self._source_table = schema
		return self._source_table

	def source_now(self) -> datetime:
		"""Current time **as the source DB sees it** (never the worker's clock)."""
		with self.source_conn.cursor() as cursor:
			cursor.execute("SELECT statement_timestamp()")
			return cursor.fetchone()[0]

	# -------------------------------------------------------------------- plan

	def plan(self, upper_bound: datetime | None = None) -> ExtractionPlan:
		raise NotImplementedError

	# ------------------------------------------------------------------- read

	def extract(self, upper_bound: datetime | None = None) -> ExtractionResult:
		"""
		Copy the planned rows out of the source into a spooled CSV buffer.

		The watermark is *not* moved here -- `commit()` does that, so it only
		advances after the rows actually landed in staging.
		"""
		plan = self.plan(upper_bound)
		extracted_at = self.source_now()
		buffer: IO[bytes] = tempfile.SpooledTemporaryFile(max_size=self.spool_max_bytes)

		try:
			with self.source_conn.cursor() as cursor:
				copy_sql = self._copy_out_sql(cursor, plan)
				logger.info("[%s] %s", plan.label, copy_sql)
				cursor.copy_expert(copy_sql, buffer, size=COPY_BUFFER_SIZE)
				row_count = cursor.rowcount
		except BaseException:
			buffer.close()
			raise

		byte_count = buffer.tell()
		buffer.seek(0)

		logger.info(
			"[%s] %s extract copied %s rows / %.1f MiB (watermark from %s)",
			plan.label,
			"FULL" if plan.is_full_load else "INCREMENTAL",
			row_count,
			byte_count / 1024 / 1024,
			plan.watermark_from,
		)
		return ExtractionResult(
			plan=plan,
			csv=buffer,
			row_count=row_count if row_count is not None and row_count >= 0 else 0,
			byte_count=byte_count,
			extracted_at=extracted_at,
		)

	def _copy_out_sql(self, cursor, plan: ExtractionPlan) -> str:
		# copy_expert() takes no parameters, so the watermark bounds are bound with
		# mogrify() -- psycopg2 still does the quoting/adaptation, so this is not
		# string concatenation of untrusted values.
		inner = plan.query
		if plan.params:
			inner = cursor.mogrify(plan.query, plan.params).decode()
		return f"COPY (\n{inner}\n) TO STDOUT WITH (FORMAT csv)"

	# ------------------------------------------------------------- bookkeeping

	def _next_watermark(
		self,
		plan: ExtractionPlan,
		observed_watermark: datetime | None,
		extracted_at: datetime,
	) -> datetime | None:
		raise NotImplementedError

	def commit(
		self,
		result: ExtractionResult,
		observed_watermark: datetime | None = None,
		row_count: int | None = None,
	) -> None:
		"""
		Persist the new watermark. Call **after** the load succeeded.

		`observed_watermark` is the highest watermark value the loader actually
		wrote into staging (`LoadStats.observed_watermark`).  Deriving the new
		watermark from loaded data rather than from a clock means nothing can slip
		through the gap between the query and the timestamp.
		"""
		watermark = self._next_watermark(result.plan, observed_watermark, result.extracted_at)
		if watermark is None:
			logger.info("[%s] nothing new loaded -- watermark stays at %s", self.label, result.plan.watermark_from)
			return

		self.wm_manager.update_watermark(
			self.source_system,
			self.schema_name,
			self.table_name,
			watermark,
			row_count=result.row_count if row_count is None else row_count,
		)

	def mark_failed(self, error: BaseException | str | None = None) -> None:
		"""Flag the run as failed; the watermark is left where it was."""
		self.wm_manager.mark_failed(
			self.source_system,
			self.schema_name,
			self.table_name,
			error=None if error is None else str(error)[:2000],
		)


class IncrementalExtractor(BaseExtractor):
	"""
	Watermark based extraction.

	* No watermark stored yet -> the whole table is read, **without** any
		predicate, so rows whose watermark column is NULL are picked up too.
	* Watermark stored -> only `watermark_expr > last_watermark` is read.

	`fallback_watermark_col` handles sources such as iccoli, where
	`update_datetime` stays NULL until a row is actually updated: the predicate
	then runs on `COALESCE(update_datetime, create_datetime)`, so freshly created
	rows are not missed and updated rows come back again.

	`overlap` re-reads a safety window below the last watermark, for tables where
	rows can commit out of watermark order (long running transactions).  The
	loader upserts on the primary key, so replayed rows are harmless.
	"""

	load_type = LOAD_TYPE_INCREMENTAL

	def __init__(
		self,
		source_conn,
		meta_conn=None,
		source_system: str = "",
		schema_name: str = "",
		table_name: str = "",
		watermark_col: str = "",
		fallback_watermark_col: str | None = None,
		*,
		exclude_columns: tuple[str, ...] = (),
		spool_max_bytes: int = DEFAULT_SPOOL_MAX_BYTES,
		overlap: timedelta = timedelta(0),
		watermark_manager: WatermarkManager | None = None,
	):
		super().__init__(
			source_conn,
			meta_conn,
			source_system,
			schema_name,
			table_name,
			exclude_columns=exclude_columns,
			spool_max_bytes=spool_max_bytes,
			watermark_manager=watermark_manager,
		)
		if not watermark_col:
			raise ValueError(f"[{self.label}] incremental extraction needs a `watermark_col`")
		excluded_watermarks = set(self.exclude_columns) & {watermark_col, fallback_watermark_col}
		if excluded_watermarks:
			raise ValueError(
				f"[{self.label}] cannot exclude {sorted(excluded_watermarks)}: the incremental "
				f"predicate reads it"
			)
		self.watermark_col = watermark_col  # e.g. 'update_datetime' or 'create_datetime'
		self.fallback_watermark_col = fallback_watermark_col  # used where watermark_col is NULL
		self.overlap = overlap

	@property
	def watermark_expr(self) -> str:
		"""`COALESCE("update_datetime", "create_datetime")` when a fallback is declared."""
		column = quote_ident(self.watermark_col)
		if self.fallback_watermark_col:
			return f"COALESCE({column}, {quote_ident(self.fallback_watermark_col)})"
		return column

	def plan(self, upper_bound: datetime | None = None) -> ExtractionPlan:
		source_table = self.describe()
		# Fail on a config typo here rather than with a bare SQL error mid-COPY.
		source_table.column(self.watermark_col)
		if self.fallback_watermark_col:
			source_table.column(self.fallback_watermark_col)

		last_wm = self.wm_manager.get_last_watermark(self.source_system, self.schema_name, self.table_name)

		conditions: list[str] = []
		params: list[Any] = []

		if last_wm is not None:
			conditions.append(f"{self.watermark_expr} > %s")
			params.append(last_wm - self.overlap)
		if upper_bound is not None:
			conditions.append(f"{self.watermark_expr} <= %s")
			params.append(upper_bound)

		predicate = "\n  AND ".join(conditions) if conditions else None
		query = f"SELECT {source_table.quoted_columns}\nFROM {self.qualified_name}"
		if predicate:
			query += f"\nWHERE {predicate}"

		return ExtractionPlan(
			source_system=self.source_system,
			schema_name=self.schema_name,
			table_name=self.table_name,
			load_type=self.load_type,
			source_table=source_table,
			query=query,
			params=tuple(params),
			predicate=predicate,
			watermark_expr=self.watermark_expr,
			watermark_from=last_wm,
			upper_bound=upper_bound,
		)

	def _next_watermark(
		self,
		plan: ExtractionPlan,
		observed_watermark: datetime | None,
		extracted_at: datetime,
	) -> datetime | None:
		if observed_watermark is not None:
			return observed_watermark
		if plan.is_full_load:
			# First run and nothing to anchor on (empty table, or every watermark
			# value is NULL). Anchor on the source clock, otherwise the table would
			# full-load again on every single run.
			return extracted_at
		# Nothing new since the last run -- leave the watermark where it is.
		return None


class FullRefreshExtractor(BaseExtractor):
	"""
	Truncate & reload targets: the whole table is read on every run.

	Used for the small reference / meta tables declared in
	`*_FULL_REFRESH_TARGETS`, which carry no reliable update timestamp.  The
	watermark row is still maintained, purely as a record of the last successful
	run.
	"""

	load_type = LOAD_TYPE_FULL_REFRESH

	def plan(self, upper_bound: datetime | None = None) -> ExtractionPlan:
		source_table = self.describe()
		return ExtractionPlan(
			source_system=self.source_system,
			schema_name=self.schema_name,
			table_name=self.table_name,
			load_type=self.load_type,
			source_table=source_table,
			query=f"SELECT {source_table.quoted_columns}\nFROM {self.qualified_name}",
			params=(),
			predicate=None,
			watermark_expr=None,
			watermark_from=None,
			upper_bound=None,
		)

	def _next_watermark(
		self,
		plan: ExtractionPlan,
		observed_watermark: datetime | None,
		extracted_at: datetime,
	) -> datetime | None:
		return extracted_at


def build_extractor(
	source_conn,
	meta_conn=None,
	source_system: str = "",
	target: Mapping[str, Any] | None = None,
	*,
	spool_max_bytes: int = DEFAULT_SPOOL_MAX_BYTES,
	overlap: timedelta = timedelta(0),
	watermark_manager: WatermarkManager | None = None,
) -> BaseExtractor:
	"""Build the extractor a single normalised config target asks for."""
	if target is None:
		raise ValueError("`target` is required")

	source_system = target.get("source_system", source_system)
	load_type = target.get("load_type", LOAD_TYPE_INCREMENTAL)
	common = dict(
		source_conn=source_conn,
		meta_conn=meta_conn,
		source_system=source_system,
		schema_name=target["schema_name"],
		table_name=target["table_name"],
		exclude_columns=tuple(target.get("exclude_columns") or ()),
		spool_max_bytes=spool_max_bytes,
		watermark_manager=watermark_manager,
	)

	if load_type == LOAD_TYPE_FULL_REFRESH:
		return FullRefreshExtractor(**common)
	if load_type != LOAD_TYPE_INCREMENTAL:
		raise ValueError(f"Unknown load_type {load_type!r} for {target['schema_name']}.{target['table_name']}")

	return IncrementalExtractor(
		**common,
		watermark_col=target["watermark_col"],
		fallback_watermark_col=target.get("fallback_watermark_col"),
		overlap=overlap,
	)


def build_extractors(
	source_conn,
	meta_conn,
	source_system: str,
	*,
	targets: list[Mapping[str, Any]] | None = None,
	spool_max_bytes: int = DEFAULT_SPOOL_MAX_BYTES,
	overlap: timedelta = timedelta(0),
) -> list[BaseExtractor]:
	"""
	Build one extractor per table declared for `source_system` in the config.

	All extractors share a single `WatermarkManager` (and therefore a single
	metadata connection), so the `stg_meta.watermarks` bootstrap runs once.
	"""
	targets = get_extraction_targets(source_system) if targets is None else targets
	watermark_manager = WatermarkManager(meta_db_conn=meta_conn)

	return [
		build_extractor(
			source_conn,
			source_system=source_system,
			target=target,
			spool_max_bytes=spool_max_bytes,
			overlap=overlap,
			watermark_manager=watermark_manager,
		)
		for target in targets
	]

"""
Staging loader.

Takes the CSV buffer an extractor produced and streams it into the warehouse:

	CREATE TEMP TABLE tmp (LIKE stg_iccoli.tb_user_info INCLUDING DEFAULTS) ON COMMIT DROP;
	COPY tmp ("user_no", ...) FROM STDIN WITH (FORMAT csv);

	-- incremental: re-delivered rows overwrite their previous version
	INSERT INTO stg_iccoli.tb_user_info ("user_no", ..., "_loaded_at")
	SELECT "user_no", ..., CURRENT_TIMESTAMP FROM tmp
	ON CONFLICT ("user_no") DO UPDATE SET ... ;

	-- full refresh: truncate and reload, atomically
	TRUNCATE TABLE stg_iccoli.tb_user_info;
	INSERT INTO stg_iccoli.tb_user_info (...) SELECT ... FROM tmp;

	-- incremental with no primary key upstream: clear the same window first,
	-- so replaying a run cannot append the rows twice
	DELETE FROM stg_discovery.disc_lifelog_user_sleep_detail WHERE "measure_end_dt" > %s;
	INSERT INTO stg_discovery.disc_lifelog_user_sleep_detail (...) SELECT ... FROM tmp;

Staging tables are created from the **source catalog**, so no DDL is maintained
by hand.  Types are copied verbatim except for types the warehouse does not have
(enums, domains, composites, extension types), which become `text` -- see
`invites_loop_bi.extract.introspect`.

The whole load runs in one transaction.  A failure therefore leaves staging
exactly as it was, and since the watermark is only committed afterwards, the next
run replays the same rows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from invites_loop_bi.config import LOAD_TYPE_FULL_REFRESH, LOAD_TYPE_INCREMENTAL
from invites_loop_bi.config.settings import LOADED_AT_COLUMN, staging_schema_for
from invites_loop_bi.extract.extractor import COPY_BUFFER_SIZE, ExtractionResult
from invites_loop_bi.extract.introspect import (
	TableNotFound,
	TableSchema,
	describe_table,
	quote_ident,
)

logger = logging.getLogger(__name__)


@dataclass
class LoadStats:
	"""Outcome of loading one extraction into staging."""

	target: str
	load_type: str
	#: Rows the temp table received from the CSV buffer.
	rows_copied: int
	#: Rows the merge inserted or updated in the staging table.
	rows_loaded: int
	#: Highest watermark value among the rows just loaded -- what the extractor
	#: commits as the new watermark. None for full refresh / empty loads.
	observed_watermark: datetime | None = None
	created_table: bool = False
	added_columns: tuple[str, ...] = ()
	truncated: bool = False
	#: Rows removed before insert to keep a keyless table idempotent.
	rows_deleted: int = 0


class StagingLoader:
	"""
	Loads extraction results into `stg_<source_system>.<table>` in the warehouse.

	The connection must **not** be in autocommit mode: the temp table, the merge
	and (for full refresh) the truncate have to share one transaction.
	"""

	def __init__(
		self,
		staging_conn,
		*,
		staging_schema: str | None = None,
		loaded_at_column: str = LOADED_AT_COLUMN,
		create_tables: bool = True,
		truncate_on_empty: bool = False,
	):
		if getattr(staging_conn, "autocommit", False):
			raise ValueError(
				"StagingLoader needs a non-autocommit connection: `ON COMMIT DROP` temp tables "
				"and the truncate+insert of a full refresh must share one transaction"
			)
		self.conn = staging_conn
		#: Override the `stg_<source_system>` convention (mainly for testing).
		self.staging_schema = staging_schema
		self.loaded_at_column = loaded_at_column
		self.create_tables = create_tables
		#: A full refresh that extracted 0 rows leaves staging alone by default,
		#: rather than emptying it on the strength of a suspiciously empty read.
		self.truncate_on_empty = truncate_on_empty
		self._temp_counter = 0

	# ------------------------------------------------------------------ naming

	def target_for(self, result: ExtractionResult) -> tuple[str, str]:
		schema = self.staging_schema or staging_schema_for(result.source_system)
		return schema, result.table_name

	def _qualified(self, schema_name: str, table_name: str) -> str:
		return f"{quote_ident(schema_name)}.{quote_ident(table_name)}"

	def _temp_table_name(self, table_name: str) -> str:
		self._temp_counter += 1
		return quote_ident(f"tmp_{self._temp_counter}_{table_name}"[:63])

	# -------------------------------------------------------------------- load

	def load(self, result: ExtractionResult) -> LoadStats:
		plan = result.plan
		source_table = result.source_table
		target_schema, target_table = self.target_for(result)
		target = self._qualified(target_schema, target_table)

		if plan.load_type == LOAD_TYPE_INCREMENTAL and not source_table.primary_key:
			logger.warning(
				"%s has no primary key, so re-delivered rows cannot be upserted. Falling back to "
				"delete-and-insert over the extracted watermark window.",
				source_table.qualified_name,
			)
		if self.loaded_at_column in source_table.column_names:
			raise ValueError(
				f"{source_table.qualified_name} already has a {self.loaded_at_column!r} column, "
				f"which collides with the loader's bookkeeping column"
			)

		try:
			created, added = self._ensure_table(source_table, target_schema, target_table)

			if result.is_empty:
				stats = self._load_nothing(result, target, created, added)
			else:
				stats = self._copy_and_merge(result, source_table, target)
				stats.created_table = created
				stats.added_columns = added

			self.conn.commit()
		except BaseException:
			self.conn.rollback()
			raise

		logger.info(
			"[%s] %s loaded %s rows into %s (watermark observed: %s)",
			plan.label,
			plan.load_type,
			stats.rows_loaded,
			target,
			stats.observed_watermark,
		)
		return stats

	def _load_nothing(
		self,
		result: ExtractionResult,
		target: str,
		created: bool,
		added: tuple[str, ...],
	) -> LoadStats:
		if result.load_type == LOAD_TYPE_FULL_REFRESH and not self.truncate_on_empty:
			logger.warning(
				"[%s] full refresh extracted 0 rows -- leaving %s as it is. Pass "
				"truncate_on_empty=True if an empty source really should empty staging.",
				result.plan.label,
				target,
			)
		else:
			logger.info("[%s] nothing to load into %s", result.plan.label, target)

		return LoadStats(
			target=target,
			load_type=result.load_type,
			rows_copied=0,
			rows_loaded=0,
			observed_watermark=None,
			created_table=created,
			added_columns=added,
		)

	def _copy_and_merge(self, result: ExtractionResult, source_table: TableSchema, target: str) -> LoadStats:
		plan = result.plan
		temp_table = self._temp_table_name(result.table_name)
		columns = source_table.quoted_columns

		with self.conn.cursor() as cursor:
			# INCLUDING DEFAULTS so the NOT NULL `_loaded_at` column gets its default
			# during COPY, which only fills the source columns.
			cursor.execute(f"CREATE TEMP TABLE {temp_table} (LIKE {target} INCLUDING DEFAULTS) ON COMMIT DROP")

			copy_sql = f"COPY {temp_table} ({columns}) FROM STDIN WITH (FORMAT csv)"
			logger.info("[%s] %s", plan.label, copy_sql)
			cursor.copy_expert(copy_sql, result.csv, size=COPY_BUFFER_SIZE)
			rows_copied = cursor.rowcount

			observed_watermark = self._observed_watermark(cursor, plan, temp_table)

			truncated = False
			rows_deleted = 0
			if plan.load_type == LOAD_TYPE_FULL_REFRESH:
				cursor.execute(f"TRUNCATE TABLE {target}")
				truncated = True
			elif not source_table.primary_key:
				truncated, rows_deleted = self._clear_window(cursor, plan, target)

			merge_sql = self._merge_sql(source_table, target, temp_table, plan.load_type)
			logger.debug("[%s] %s", plan.label, merge_sql)
			cursor.execute(merge_sql)
			rows_loaded = cursor.rowcount

		return LoadStats(
			target=target,
			load_type=plan.load_type,
			rows_copied=max(rows_copied or 0, 0),
			rows_loaded=max(rows_loaded or 0, 0),
			observed_watermark=observed_watermark,
			truncated=truncated,
			rows_deleted=rows_deleted,
		)

	def _clear_window(self, cursor, plan, target: str) -> tuple[bool, int]:
		"""
		Make a keyless incremental load idempotent.

		Without a primary key there is nothing to upsert on, so a replayed run
		would append the same rows again. Instead the loader removes exactly the
		window the extractor read -- the plan's own predicate, replayed against
		staging with the same bounds -- and then inserts. Re-running any window
		therefore leaves staging in the same state.

		Returns `(truncated, rows_deleted)`.
		"""
		if not plan.predicate:
			# A full read (first run): everything is about to be re-inserted.
			cursor.execute(f"TRUNCATE TABLE {target}")
			return True, 0

		cursor.execute(f"DELETE FROM {target}\nWHERE {plan.predicate}", plan.params)
		return False, max(cursor.rowcount or 0, 0)

	def _observed_watermark(self, cursor, plan, temp_table: str) -> datetime | None:
		"""
		Highest watermark value among the rows just copied.

		Read from the temp table rather than from the source: it costs no extra
		source scan and describes exactly what was loaded.
		"""
		if not plan.watermark_expr:
			return None
		cursor.execute(f"SELECT max({plan.watermark_expr}) FROM {temp_table}")
		return cursor.fetchone()[0]

	def _merge_sql(self, source_table: TableSchema, target: str, temp_table: str, load_type: str) -> str:
		loaded_at = quote_ident(self.loaded_at_column)
		insert_columns = ", ".join([source_table.quoted_columns, loaded_at])
		select_columns = ", ".join([source_table.quoted_columns, "CURRENT_TIMESTAMP"])

		sql = (
			f"INSERT INTO {target} ({insert_columns})\n"
			f"SELECT {select_columns}\n"
			f"FROM {temp_table}"
		)

		# A full refresh truncated the table first, so nothing can conflict.
		if load_type != LOAD_TYPE_INCREMENTAL or not source_table.primary_key:
			return sql

		primary_key = ", ".join(quote_ident(name) for name in source_table.primary_key)
		updatable = [
			column.quoted_name
			for column in source_table.columns
			if column.name not in source_table.primary_key
		]
		if not updatable:
			# Every column is part of the key -- there is nothing to overwrite.
			return f"{sql}\nON CONFLICT ({primary_key}) DO NOTHING"

		assignments = ", ".join(f"{name} = EXCLUDED.{name}" for name in [*updatable, loaded_at])
		return f"{sql}\nON CONFLICT ({primary_key}) DO UPDATE SET {assignments}"

	# --------------------------------------------------------------------- DDL

	def _ensure_table(
		self,
		source_table: TableSchema,
		target_schema: str,
		target_table: str,
	) -> tuple[bool, tuple[str, ...]]:
		"""
		Create the staging table if missing, or add columns the source has grown.

		Returns `(created, added_columns)`.  Columns dropped or retyped upstream are
		only logged: staging keeps them, and the loader simply stops writing them.
		"""
		target = self._qualified(target_schema, target_table)

		with self.conn.cursor() as cursor:
			cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {quote_ident(target_schema)}")

		try:
			existing = describe_table(self.conn, target_schema, target_table)
		except TableNotFound:
			if not self.create_tables:
				raise
			with self.conn.cursor() as cursor:
				cursor.execute(self._create_table_sql(source_table, target))
			logger.info("Created staging table %s (%s columns)", target, len(source_table.columns))
			return True, ()

		known = set(existing.column_names)
		missing = [column for column in source_table.columns if column.name not in known]
		if missing:
			with self.conn.cursor() as cursor:
				for column in missing:
					cursor.execute(f"ALTER TABLE {target} ADD COLUMN {column.quoted_name} {column.staging_type}")
			logger.warning(
				"Source schema drift: added %s to %s",
				", ".join(f"{column.name} {column.staging_type}" for column in missing),
				target,
			)

		dropped = known - set(source_table.column_names) - {self.loaded_at_column}
		if dropped:
			logger.warning(
				"%s has columns the source no longer exposes: %s (left in place, no longer written)",
				target,
				", ".join(sorted(dropped)),
			)

		return False, tuple(column.name for column in missing)

	def _create_table_sql(self, source_table: TableSchema, target: str) -> str:
		definitions = [f"{column.quoted_name} {column.staging_type}" for column in source_table.columns]
		definitions.append(f"{quote_ident(self.loaded_at_column)} timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP")
		if source_table.primary_key:
			primary_key = ", ".join(quote_ident(name) for name in source_table.primary_key)
			definitions.append(f"PRIMARY KEY ({primary_key})")

		body = ",\n\t".join(definitions)
		return f"CREATE TABLE IF NOT EXISTS {target} (\n\t{body}\n)"

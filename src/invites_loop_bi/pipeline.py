"""
Pipeline entry point: extract -> load -> commit, for one table or a whole system.

The ordering is the whole point:

1. `extract()` copies the source rows out into a CSV buffer.
2. `load()` streams them into staging, in one transaction.
3. `commit()` moves the watermark -- and only then.

A failure anywhere leaves staging untouched (the load transaction rolls back) and
the watermark where it was, so the next run replays exactly the same window. The
load is idempotent either way: upsert on the primary key, or delete-and-insert
over the window for the handful of sources that have no key.

Run it by hand:

	uv run python -m invites_loop_bi.pipeline iccoli --dry-run
	uv run python -m invites_loop_bi.pipeline iccoli --table tb_action_mapper
	uv run python -m invites_loop_bi.pipeline discovery --overlap-minutes 5
"""

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta

from invites_loop_bi.config import SOURCE_SYSTEMS, get_extraction_targets
from invites_loop_bi.config.settings import check_timezone_alignment
from invites_loop_bi.connections import open_connections
from invites_loop_bi.extract import WatermarkManager, WatermarkStore, build_extractor
from invites_loop_bi.load import StagingLoader

logger = logging.getLogger(__name__)


@dataclass
class TableRunResult:
	"""What one table's run did, whether it worked or not."""

	source_system: str
	schema_name: str
	table_name: str
	load_type: str
	rows_extracted: int = 0
	rows_loaded: int = 0
	rows_deleted: int = 0
	created_table: bool = False
	added_columns: tuple[str, ...] = ()
	watermark: datetime | None = None
	error: str | None = None

	@property
	def ok(self) -> bool:
		return self.error is None

	@property
	def label(self) -> str:
		return f"{self.source_system}.{self.schema_name}.{self.table_name}"

	def summary(self) -> str:
		if not self.ok:
			return f"{self.label}: FAILED -- {self.error}"
		extras = []
		if self.created_table:
			extras.append("created")
		if self.added_columns:
			extras.append(f"+{len(self.added_columns)} columns")
		if self.rows_deleted:
			extras.append(f"-{self.rows_deleted} replaced")
		suffix = f" ({', '.join(extras)})" if extras else ""
		return f"{self.label}: {self.rows_loaded} rows -> watermark {self.watermark}{suffix}"


def run_table(
	source_conn,
	warehouse_conn,
	source_system: str,
	target: dict,
	*,
	loader: StagingLoader | None = None,
	watermark_manager: WatermarkStore | None = None,
	overlap: timedelta = timedelta(0),
	upper_bound: datetime | None = None,
) -> TableRunResult:
	"""
	Move one table's new rows into staging.

	Raises on failure, after recording it in `stg_meta.watermarks`. Airflow maps
	one task per table onto this, so a raise is what marks that task failed and
	leaves the other tables alone.
	"""
	extractor = build_extractor(
		source_conn,
		warehouse_conn,
		source_system=source_system,
		target=target,
		overlap=overlap,
		watermark_manager=watermark_manager,
	)
	loader = loader or StagingLoader(warehouse_conn)

	try:
		with extractor.extract(upper_bound=upper_bound) as result:
			stats = loader.load(result)
			extractor.commit(result, stats.observed_watermark, stats.rows_loaded)

			return TableRunResult(
				source_system=source_system,
				schema_name=target["schema_name"],
				table_name=target["table_name"],
				load_type=result.load_type,
				rows_extracted=result.row_count,
				rows_loaded=stats.rows_loaded,
				rows_deleted=stats.rows_deleted,
				created_table=stats.created_table,
				added_columns=stats.added_columns,
				watermark=stats.observed_watermark,
			)
	except BaseException as exc:
		# The load rolled itself back; record the failure without moving the
		# watermark, so the next run picks the same window up again.
		extractor.mark_failed(exc)
		raise


def run_source_system(
	source_conn,
	warehouse_conn,
	source_system: str,
	*,
	targets: list[dict] | None = None,
	overlap: timedelta = timedelta(0),
	upper_bound: datetime | None = None,
	fail_fast: bool = False,
) -> list[TableRunResult]:
	"""
	Run every table configured for a source system, sequentially.

	One broken table does not stop the rest unless `fail_fast` is set; failures
	come back in the results. Airflow parallelises across tables instead, so this
	is mainly for local runs and backfills.
	"""
	targets = get_extraction_targets(source_system) if targets is None else targets
	check_timezone_alignment(source_conn, warehouse_conn)

	# Shared, so the metadata bootstrap and the loader setup happen once.
	watermark_manager = WatermarkManager(meta_db_conn=warehouse_conn)
	loader = StagingLoader(warehouse_conn)

	results: list[TableRunResult] = []
	for target in targets:
		try:
			result = run_table(
				source_conn,
				warehouse_conn,
				source_system,
				target,
				loader=loader,
				watermark_manager=watermark_manager,
				overlap=overlap,
				upper_bound=upper_bound,
			)
		except Exception as exc:
			if fail_fast:
				raise
			logger.exception("[%s.%s] failed", source_system, target["table_name"])
			result = TableRunResult(
				source_system=source_system,
				schema_name=target["schema_name"],
				table_name=target["table_name"],
				load_type=target["load_type"],
				error=f"{type(exc).__name__}: {exc}",
			)
		results.append(result)
		logger.info(result.summary())

	failed = [r for r in results if not r.ok]
	logger.info(
		"[%s] %s/%s tables loaded, %s rows total%s",
		source_system,
		len(results) - len(failed),
		len(results),
		sum(r.rows_loaded for r in results),
		f", {len(failed)} FAILED" if failed else "",
	)
	return results


def describe_plan(source_conn, warehouse_conn, source_system: str, targets: list[dict] | None = None) -> list[str]:
	"""
	The SQL each table would run, without extracting anything.

	Read-only on both sides: the watermark table is not created if it is missing,
	so a dry run against the warehouse leaves no trace.
	"""
	targets = get_extraction_targets(source_system) if targets is None else targets
	watermark_manager = WatermarkManager(meta_db_conn=warehouse_conn, ensure_table=False)

	lines = []
	for target in targets:
		extractor = build_extractor(
			source_conn,
			source_system=source_system,
			target=target,
			watermark_manager=watermark_manager,
		)
		plan = extractor.plan()
		mode = "FULL" if plan.is_full_load else "INCREMENTAL"
		lines.append(f"-- {plan.label} [{plan.load_type}/{mode}] from {plan.watermark_from}\n{plan.query}")
	return lines


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument("source_system", choices=sorted(SOURCE_SYSTEMS))
	parser.add_argument("--table", action="append", dest="tables", help="only this table (repeatable)")
	parser.add_argument("--overlap-minutes", type=float, default=0.0, help="re-read this far below the watermark")
	parser.add_argument("--dry-run", action="store_true", help="print the SQL each table would run, then stop")
	parser.add_argument("--fail-fast", action="store_true", help="stop at the first failing table")
	parser.add_argument("--log-level", default="INFO")
	args = parser.parse_args(argv)

	logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(levelname)-7s %(message)s")

	targets = get_extraction_targets(args.source_system)
	if args.tables:
		wanted = set(args.tables)
		targets = [t for t in targets if t["table_name"] in wanted]
		missing = wanted - {t["table_name"] for t in targets}
		if missing:
			parser.error(f"not configured for {args.source_system}: {sorted(missing)}")

	with open_connections(args.source_system) as (source_conn, warehouse_conn):
		if args.dry_run:
			for block in describe_plan(source_conn, warehouse_conn, args.source_system, targets):
				print(f"{block}\n")
			return 0

		results = run_source_system(
			source_conn,
			warehouse_conn,
			args.source_system,
			targets=targets,
			overlap=timedelta(minutes=args.overlap_minutes),
			fail_fast=args.fail_fast,
		)

	for result in results:
		print(result.summary())
	return 1 if any(not r.ok for r in results) else 0


if __name__ == "__main__":
	sys.exit(main())

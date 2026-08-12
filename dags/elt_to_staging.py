"""
Source databases -> warehouse staging.

One DAG per source system, one dynamically mapped task per configured table:

	elt_iccoli_to_staging      34 tables   (database `iccoli`)
	elt_ichms_to_staging       16 tables  -\\
	elt_sibc_to_staging        36 tables   |  schemas inside `invites_loop`
	elt_irs_to_staging          5 tables   |
	elt_discovery_to_staging   32 tables  -/

Adding a table to a pipeline means adding an entry to
`invites_loop_bi.config.<system>_targets`; no change is needed here.

Each mapped task owns its own connections and its own transaction, so one bad
table fails alone and retries alone. Watermarks live in `stg_meta.watermarks` and
only advance after a table's rows are committed to staging, which makes a retry
replay the same window rather than skip it.
"""

from datetime import datetime, timedelta

import pendulum
from airflow.sdk import dag, get_current_context, task

from invites_loop_bi.config import SOURCE_SYSTEMS, get_extraction_targets
from invites_loop_bi.connections import open_connections
from invites_loop_bi.pipeline import run_table

KST = pendulum.timezone("Asia/Seoul")

#: 01:00 KST, one hour ahead of `transform_dbt_build` (02:00 KST). KST rather
#: than UTC because `ymd` is a business date on a KST midnight boundary -- a UTC
#: schedule would straddle it.
#:
#: Daily, not hourly: the marts rebuild once a day, so more frequent extraction
#: would only add source-database load for numbers nobody reads until tomorrow.
#: Raise the frequency when something downstream actually needs intraday data.
SCHEDULE = "0 1 * * *"
START_DATE = datetime(2026, 1, 1, tzinfo=KST)

#: Tables loaded concurrently per system. Every one of them holds a source
#: connection and a COPY, so this is the main dial for source DB load.
MAX_PARALLEL_TABLES = 4

#: Re-read this far below the last watermark. Rows committed out of watermark
#: order (long transactions upstream) would otherwise be missed; the load is
#: idempotent, so replaying them is free. Raise it if rows ever go missing.
OVERLAP = timedelta(minutes=5)

DEFAULT_ARGS = {
	"retries": 2,
	"retry_delay": timedelta(minutes=5),
	"depends_on_past": False,
}


def _set_map_index_name(context, table_name: str) -> None:
	"""Write the mapped-task label into Airflow's runtime context."""
	context["table_name"] = table_name


def build_dag(source_system: str):
	@dag(
		dag_id=f"elt_{source_system}_to_staging",
		description=f"Extract {source_system} into stg_{source_system} in the warehouse",
		schedule=SCHEDULE,
		start_date=START_DATE,
		catchup=False,
		# Two runs at once would read the same watermark and do the same work twice.
		max_active_runs=1,
		max_active_tasks=MAX_PARALLEL_TABLES,
		default_args=DEFAULT_ARGS,
		tags=["elt", "staging", source_system],
	)
	def elt_dag():
		@task
		def list_targets() -> list[dict]:
			"""The tables configured for this system, incremental and full refresh."""
			return get_extraction_targets(source_system)

		@task(map_index_template="{{ table_name }}")
		def extract_and_load(target: dict) -> dict:
			# Name the mapped task after its table instead of an index.
			# Airflow's context type is closed; map_index_template still reads
			# this key from the runtime context dict.
			_set_map_index_name(get_current_context(), target["table_name"])

			with open_connections(source_system) as (source_conn, warehouse_conn):
				result = run_table(source_conn, warehouse_conn, source_system, target, overlap=OVERLAP)

			# XCom has to be JSON friendly, so hand back a plain summary.
			return {
				"table": result.label,
				"load_type": result.load_type,
				"rows_extracted": result.rows_extracted,
				"rows_loaded": result.rows_loaded,
				"rows_replaced": result.rows_deleted,
				"created_table": result.created_table,
				"added_columns": list(result.added_columns),
				"watermark": result.watermark.isoformat() if result.watermark else None,
			}

		extract_and_load.expand(target=list_targets())

	return elt_dag()


for _source_system in SOURCE_SYSTEMS:
	globals()[f"elt_{_source_system}_to_staging"] = build_dag(_source_system)

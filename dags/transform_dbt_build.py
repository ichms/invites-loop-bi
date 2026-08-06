"""
Warehouse staging -> dbt staging views -> marts.

One `dbt build` (models + tests + seeds) in a single BashOperator, per D-02: 20
models does not justify task-level granularity, and `ref()` already handles
build order. Hand-maintained Airflow task dependencies drift and produce
stale-but-plausible numbers, which is the failure mode this whole design exists
to avoid.

Scheduling: the five ELT DAGs run at 01:00 KST, this one at 02:00 KST
(IMPLEMENTATION_PLAN.md §3.3). A fixed offset rather than Airflow 3 asset
triggering, deliberately — the offset is one line in the runbook and one line
here, and a junior debugging "why did the transform not run" can read a cron
expression. One hour is generous: the full ELT is minutes today.

Two tasks, not one:
  1. `dbt_source_freshness` — the stalled-ELT tripwire. Runs FIRST and does not
     block the build (`|| true`): a stale source should be loud, but yesterday's
     numbers rebuilt is better than no numbers at all. The task's own state is
     what carries the signal.
  2. `dbt_build` — `--fail-fast`, so a broken grain stops the build at the first
     failure instead of cascading wrong numbers through the marts.
"""

from datetime import datetime, timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag

KST = pendulum.timezone("Asia/Seoul")

#: 01:00 KST for the ELT DAGs, 02:00 KST here. Keep the gap if either side grows.
SCHEDULE = "0 2 * * *"
START_DATE = datetime(2026, 1, 1, tzinfo=KST)

#: The dbt project lives at the repo root, next to `dags/`.
DBT_PROJECT_DIR = "{{ var.value.get('dbt_project_dir', '/opt/airflow/dbt') }}"

DEFAULT_ARGS = {
	"retries": 1,
	"retry_delay": timedelta(minutes=10),
	"depends_on_past": False,
}


@dag(
	dag_id="transform_dbt_build",
	description="dbt build (staging views + marts + tests) over the warehouse landing schemas",
	schedule=SCHEDULE,
	start_date=START_DATE,
	catchup=False,
	# Two concurrent builds would write the same tables.
	max_active_runs=1,
	default_args=DEFAULT_ARGS,
	tags=["transform", "dbt", "marts"],
)
def transform_dbt_build():
	freshness = BashOperator(
		task_id="dbt_source_freshness",
		# Non-blocking on purpose (see the module docstring). The command's own
		# exit code still lands in the log for whoever reads the failure.
		bash_command=(
			f"cd {DBT_PROJECT_DIR} && "
			"dbt source freshness --project-dir . || true"
		),
	)

	build = BashOperator(
		task_id="dbt_build",
		bash_command=(
			f"cd {DBT_PROJECT_DIR} && "
			"dbt build --project-dir . --fail-fast"
		),
	)

	freshness >> build


transform_dbt_build()

"""
The DAG file must parse and cover every configured table.

Importing Airflow touches AIRFLOW_HOME, so it is pointed at a throwaway directory
before the import happens.
"""

import importlib.util
import os
import tempfile
from pathlib import Path

from invites_loop_bi.config import SOURCE_SYSTEMS, get_extraction_targets
from tests.db import skip

DAG_FILE = Path(__file__).resolve().parents[1] / "dags" / "elt_to_staging.py"


def load_dags():
	"""Import the DAG module and return the DAG objects it defines."""
	os.environ.setdefault("AIRFLOW_HOME", tempfile.mkdtemp(prefix="airflow-test-"))
	try:
		from airflow.sdk import DAG
	except ImportError:
		skip("apache-airflow is not installed")

	spec = importlib.util.spec_from_file_location("elt_to_staging_under_test", DAG_FILE)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return {dag.dag_id: dag for dag in vars(module).values() if isinstance(dag, DAG)}


def test_dag_file_parses_one_dag_per_source_system():
	dags = load_dags()
	assert set(dags) == {f"elt_{system}_to_staging" for system in SOURCE_SYSTEMS}


def test_each_dag_maps_over_its_configured_tables():
	dags = load_dags()
	for system in SOURCE_SYSTEMS:
		dag = dags[f"elt_{system}_to_staging"]
		assert {task.task_id for task in dag.tasks} == {"list_targets", "extract_and_load"}
		# the mapped task's inputs come from list_targets at runtime; assert the
		# config it will expand over is non-empty
		assert get_extraction_targets(system)


def test_concurrent_runs_are_prevented():
	"""Two runs at once would read the same watermark and duplicate the work."""
	for dag in load_dags().values():
		assert dag.max_active_runs == 1
		assert dag.max_active_tasks >= 1


def test_tables_are_retried_but_do_not_wait_on_each_other():
	for dag in load_dags().values():
		task = dag.get_task("extract_and_load")
		assert task.retries >= 1, "a transient source hiccup should not need a manual rerun"
		assert task.depends_on_past is False


def test_no_catchup_stampede():
	"""Watermarks already track position; replaying schedule intervals adds nothing."""
	for dag in load_dags().values():
		assert dag.catchup is False


def test_dags_are_tagged_for_filtering():
	for system in SOURCE_SYSTEMS:
		dag = load_dags()[f"elt_{system}_to_staging"]
		assert {"elt", "staging", system} <= set(dag.tags)

"""Orchestration: extract -> load -> commit, and what happens when it breaks."""

from invites_loop_bi.config import get_extraction_targets
from invites_loop_bi.extract import WatermarkManager
from invites_loop_bi.load import StagingLoader
from invites_loop_bi.pipeline import TableRunResult, describe_plan, run_source_system, run_table
from tests.db import sessions

TABLE = "tb_action_mapper"


def target_for(table_name=TABLE, **overrides):
	target = next(t for t in get_extraction_targets("iccoli") if t["table_name"] == table_name)
	return {**target, **overrides}


# ----------------------------------------------------------------- offline


def test_result_summarises_a_successful_run():
	result = TableRunResult(
		source_system="iccoli",
		schema_name="public",
		table_name="tb_user_info",
		load_type="incremental",
		rows_loaded=42,
		created_table=True,
	)
	assert result.ok
	assert result.label == "iccoli.public.tb_user_info"
	assert "42 rows" in result.summary()
	assert "created" in result.summary()


def test_result_summarises_a_failure():
	result = TableRunResult(
		source_system="iccoli",
		schema_name="public",
		table_name="tb_user_info",
		load_type="incremental",
		error="OperationalError: connection reset",
	)
	assert not result.ok
	assert "FAILED" in result.summary()
	assert "connection reset" in result.summary()


# --------------------------------------------------------------------- db


def test_run_table_extracts_loads_and_commits():
	with sessions() as (source, dw):
		result = run_table(source, dw, "iccoli", target_for())

		assert result.ok
		assert result.rows_loaded == result.rows_extracted > 0
		assert result.created_table
		assert result.watermark is not None

		with dw.cursor() as cursor:
			cursor.execute(f"SELECT count(*) FROM stg_iccoli.{TABLE}")
			assert cursor.fetchone()[0] == result.rows_loaded

		stored = WatermarkManager(meta_db_conn=dw).get_last_watermark("iccoli", "public", TABLE)
		assert stored == result.watermark


def test_run_table_is_idempotent():
	with sessions() as (source, dw):
		first = run_table(source, dw, "iccoli", target_for())
		second = run_table(source, dw, "iccoli", target_for())

		# nothing moved upstream, so the second run has nothing to do
		assert second.rows_extracted == 0
		with dw.cursor() as cursor:
			cursor.execute(f"SELECT count(*) FROM stg_iccoli.{TABLE}")
			assert cursor.fetchone()[0] == first.rows_loaded


def test_a_failing_load_leaves_the_watermark_unmoved():
	"""The whole point of committing last: a failure must be replayable."""

	class ExplodingLoader(StagingLoader):
		def load(self, result):
			raise RuntimeError("staging is on fire")

	with sessions() as (source, dw):
		watermarks = WatermarkManager(meta_db_conn=dw)
		try:
			run_table(source, dw, "iccoli", target_for(), loader=ExplodingLoader(dw), watermark_manager=watermarks)
		except RuntimeError as exc:
			assert "on fire" in str(exc)
		else:
			raise AssertionError("run_table should propagate the failure")

		assert watermarks.get_last_watermark("iccoli", "public", TABLE) is None
		with dw.cursor() as cursor:
			cursor.execute("SELECT last_status, last_error FROM stg_meta.watermarks WHERE table_name=%s", (TABLE,))
			status, error = cursor.fetchone()
		assert status == "FAILED"
		assert "on fire" in error


def test_run_source_system_keeps_going_after_a_bad_table():
	with sessions() as (source, dw):
		broken = target_for(table_name=TABLE)
		broken = {**broken, "table_name": "tb_does_not_exist"}
		results = run_source_system(source, dw, "iccoli", targets=[target_for(), broken])

		assert len(results) == 2
		assert results[0].ok, "the healthy table should still have loaded"
		assert not results[1].ok
		assert "tb_does_not_exist" in results[1].error


def test_run_source_system_can_stop_at_the_first_failure():
	with sessions() as (source, dw):
		broken = {**target_for(), "table_name": "tb_does_not_exist"}
		try:
			run_source_system(source, dw, "iccoli", targets=[broken, target_for()], fail_fast=True)
		except Exception as exc:
			assert "tb_does_not_exist" in str(exc)
		else:
			raise AssertionError("fail_fast should re-raise")


def test_run_source_system_loads_several_tables():
	with sessions() as (source, dw):
		targets = [target_for(), target_for("tb_action_info"), target_for("tb_menu_app")]
		results = run_source_system(source, dw, "iccoli", targets=targets)

		assert all(r.ok for r in results)
		assert len({r.table_name for r in results}) == 3
		assert sum(r.rows_loaded for r in results) > 0


def test_dry_run_writes_nothing():
	"""describe_plan must not create stg_meta, so it is safe against production."""
	with sessions() as (source, dw):
		with dw.cursor() as cursor:
			cursor.execute("SELECT to_regclass('stg_meta.watermarks') IS NOT NULL")
			existed = cursor.fetchone()[0]

		plans = describe_plan(source, dw, "iccoli", targets=[target_for()])

		assert len(plans) == 1
		assert "SELECT" in plans[0]
		assert TABLE in plans[0]

		with dw.cursor() as cursor:
			cursor.execute("SELECT to_regclass('stg_meta.watermarks') IS NOT NULL")
			assert cursor.fetchone()[0] == existed, "a dry run created the watermark table"

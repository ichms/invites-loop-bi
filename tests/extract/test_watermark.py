"""Watermark bookkeeping in `stg_meta.watermarks`."""

from datetime import datetime, timezone

from invites_loop_bi.extract.watermark import WatermarkManager
from tests.fakes import RecordingConnection

WATERMARK = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
KEY = ("iccoli", "public", "tb_user_info")


def make_manager(results=None):
	connection = RecordingConnection(results)
	manager = WatermarkManager(meta_db_conn=connection)
	# forget the bootstrap DDL and its commit, so assertions see only the test's calls
	connection.executed.clear()
	connection.commits = 0
	return manager, connection


def test_bootstrap_creates_schema_and_table():
	connection = RecordingConnection()
	WatermarkManager(meta_db_conn=connection)
	bootstrap = connection.statements()[0]
	assert "CREATE SCHEMA IF NOT EXISTS stg_meta" in bootstrap
	assert "CREATE TABLE IF NOT EXISTS stg_meta.watermarks" in bootstrap
	assert connection.commits == 1


def test_no_row_means_first_run():
	manager, _ = make_manager(results=[])
	assert manager.get_last_watermark(*KEY) is None


def test_existing_watermark_is_returned():
	manager, connection = make_manager(results=[(WATERMARK, "SUCCESS")])
	assert manager.get_last_watermark(*KEY) == WATERMARK
	assert connection.executed[0][1] == KEY


def test_watermark_survives_a_failed_run():
	"""
	The regression this guards: filtering on last_status='SUCCESS' made a failed
	run look like a first run, which silently full-reloaded the whole table.
	"""
	manager, _ = make_manager(results=[(WATERMARK, "FAILED")])
	assert manager.get_last_watermark(*KEY) == WATERMARK


def test_update_upserts_watermark_and_row_count():
	manager, connection = make_manager()
	manager.update_watermark(*KEY, WATERMARK, row_count=42)

	sql, params = connection.executed[0]
	assert "INSERT INTO stg_meta.watermarks" in sql
	assert "ON CONFLICT (source_system, schema_name, table_name)" in sql
	assert "watermark_value = EXCLUDED.watermark_value" in sql
	assert params == (*KEY, WATERMARK, "SUCCESS", 42)
	assert connection.commits == 1


def test_mark_failed_records_the_error_without_moving_the_watermark():
	manager, connection = make_manager()
	manager.mark_failed(*KEY, error="connection reset")

	sql, params = connection.executed[0]
	assert "last_status = 'FAILED'" in sql
	assert "watermark_value" not in sql.split("DO UPDATE SET")[1]
	assert params == (*KEY, "connection reset")

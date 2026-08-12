"""Staging DDL, the upsert merge, and guard rails -- without a database."""

from invites_loop_bi.config.settings import staging_schema_for
from invites_loop_bi.load import StagingLoader
from tests.fakes import NullConnection, table_schema

TARGET = '"stg_iccoli"."tb_demo"'
TEMP = '"tmp_1_tb_demo"'


def make_loader():
	return StagingLoader(NullConnection())


# ------------------------------------------------------------------ naming


def test_staging_schema_follows_the_source_system():
	assert staging_schema_for("iccoli") == "stg_iccoli"
	assert staging_schema_for("discovery") == "stg_discovery"


def test_temp_table_names_are_unique_per_load():
	loader = make_loader()
	first = loader._temp_table_name("tb_demo")
	second = loader._temp_table_name("tb_demo")
	assert first != second


def test_temp_table_name_stays_a_legal_identifier():
	loader = make_loader()
	name = loader._temp_table_name("x" * 200)
	assert len(name) <= 65  # 63 characters plus the two quotes


# --------------------------------------------------------------------- DDL


def test_create_table_mirrors_the_source_and_adds_bookkeeping():
	sql = make_loader()._create_table_sql(table_schema(), TARGET)
	assert sql.startswith(f"CREATE TABLE IF NOT EXISTS {TARGET}")
	assert '"user_no" integer' in sql
	assert '"payload" jsonb' in sql
	assert '"_loaded_at" timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP' in sql
	assert 'PRIMARY KEY ("user_no")' in sql


def test_create_table_maps_types_the_warehouse_lacks_to_text():
	sql = make_loader()._create_table_sql(table_schema(), TARGET)
	assert '"status_cd" text' in sql
	assert "status_type" not in sql


def test_create_table_carries_a_composite_primary_key():
	schema = table_schema(
		columns=(("action_no", "integer"), ("relation_type", "text"), ("use_yn", "character varying")),
		primary_key=("action_no", "relation_type"),
	)
	sql = make_loader()._create_table_sql(schema, TARGET)
	assert 'PRIMARY KEY ("action_no", "relation_type")' in sql


def test_create_table_without_a_primary_key_omits_the_constraint():
	schema = table_schema(primary_key=())
	assert "PRIMARY KEY" not in make_loader()._create_table_sql(schema, TARGET)


# ------------------------------------------------------------------- merge


def test_incremental_merge_upserts_every_non_key_column():
	sql = make_loader()._merge_sql(table_schema(), TARGET, TEMP, "incremental")
	assert f"INSERT INTO {TARGET}" in sql
	assert f"FROM {TEMP}" in sql
	assert 'ON CONFLICT ("user_no") DO UPDATE SET' in sql
	for column in ('"payload"', '"status_cd"', '"update_datetime"', '"create_datetime"'):
		assert f"{column} = EXCLUDED.{column}" in sql
	assert '"_loaded_at" = EXCLUDED."_loaded_at"' in sql
	# the key itself is never overwritten
	assert '"user_no" = EXCLUDED."user_no"' not in sql


def test_merge_stamps_the_load_time():
	sql = make_loader()._merge_sql(table_schema(), TARGET, TEMP, "incremental")
	assert "CURRENT_TIMESTAMP" in sql
	assert sql.index('"_loaded_at"') < sql.index("SELECT")


def test_merge_does_nothing_when_every_column_is_part_of_the_key():
	schema = table_schema(
		columns=(("user_no", "integer"), ("visit_datetime", "timestamp with time zone")),
		primary_key=("user_no", "visit_datetime"),
	)
	sql = make_loader()._merge_sql(schema, TARGET, TEMP, "incremental")
	assert 'ON CONFLICT ("user_no", "visit_datetime") DO NOTHING' in sql


def test_full_refresh_merge_needs_no_conflict_clause():
	"""The table was truncated first, so nothing can collide."""
	sql = make_loader()._merge_sql(table_schema(), TARGET, TEMP, "full_refresh")
	assert "ON CONFLICT" not in sql


# ------------------------------------------------------------- guard rails


def test_autocommit_connection_is_rejected():
	class AutocommitConnection(NullConnection):
		autocommit = True

	try:
		StagingLoader(AutocommitConnection())
	except ValueError as exc:
		assert "autocommit" in str(exc)
	else:
		raise AssertionError("an autocommit connection cannot hold the load in one transaction")


def make_result(schema, *, predicate=None, params=(), load_type="incremental"):
	from datetime import datetime, timezone
	from io import BytesIO

	from invites_loop_bi.extract import ExtractionPlan, ExtractionResult

	plan = ExtractionPlan(
		source_system="iccoli",
		schema_name="public",
		table_name="tb_demo",
		load_type=load_type,
		source_table=schema,
		query="SELECT 1",
		params=params,
		predicate=predicate,
		watermark_expr='"update_datetime"',
		watermark_from=None,
	)
	# csv / extracted_at are unused by the SQL-generation callers; fill with
	# stand-ins so the dataclass stays correctly typed.
	return ExtractionResult(
		plan=plan,
		csv=BytesIO(),
		row_count=1,
		byte_count=1,
		extracted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
	)


def test_keyless_incremental_merge_is_a_plain_insert():
	"""Nothing to upsert on -- idempotency comes from clearing the window first."""
	sql = make_loader()._merge_sql(table_schema(primary_key=()), TARGET, TEMP, "incremental")
	assert "ON CONFLICT" not in sql
	assert f"INSERT INTO {TARGET}" in sql


def test_keyless_window_is_deleted_with_the_extractor_s_own_predicate():
	from datetime import datetime, timezone

	watermark = datetime(2026, 1, 1, tzinfo=timezone.utc)
	predicate = '"measure_end_dt" > %s'
	executed = []

	class Cursor:
		rowcount = 7

		def execute(self, sql, params=None):
			executed.append((sql, params))

	result = make_result(table_schema(primary_key=()), predicate=predicate, params=(watermark,))
	truncated, deleted = make_loader()._clear_window(Cursor(), result.plan, TARGET)

	sql, params = executed[0]
	assert sql.startswith(f"DELETE FROM {TARGET}")
	assert predicate in sql
	assert params == (watermark,), "the delete must use the same bounds the extract did"
	assert (truncated, deleted) == (False, 7)


def test_keyless_first_run_truncates_instead_of_deleting():
	"""A first run read the whole table, so every row is about to be replaced."""
	executed = []

	class Cursor:
		rowcount = -1

		def execute(self, sql, params=None):
			executed.append(sql)

	result = make_result(table_schema(primary_key=()), predicate=None)
	truncated, deleted = make_loader()._clear_window(Cursor(), result.plan, TARGET)

	assert executed == [f"TRUNCATE TABLE {TARGET}"]
	assert (truncated, deleted) == (True, 0)


def test_source_column_colliding_with_the_bookkeeping_column_is_refused():
	schema = table_schema(columns=(("user_no", "integer"), ("_loaded_at", "timestamp with time zone")))
	try:
		make_loader().load(make_result(schema))
	except ValueError as exc:
		assert "_loaded_at" in str(exc)
	else:
		raise AssertionError("a colliding _loaded_at column should be refused")

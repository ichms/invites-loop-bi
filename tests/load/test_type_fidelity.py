"""
Every awkward column type must arrive in staging byte-identical.

These are the types that made a dataframe hop unsafe -- `jsonb` (a Struct unions
the keys of every row in a batch), enums (absent from the warehouse), `interval`,
`numeric` (float rounding) and naive `timestamp` (timezone drift). `COPY ... CSV`
carries PostgreSQL's own text representation, so all of them should survive.

Values are compared programmatically and never printed: some of these tables hold
personal data. Rolled back at the end.
"""

from datetime import timedelta

from invites_loop_bi.config import get_extraction_targets
from invites_loop_bi.extract import build_extractor
from invites_loop_bi.load import StagingLoader
from tests.db import reset_staging, sessions
from tests.fakes import StubWatermarkManager

#: table -> the type it is here to prove
CASES = {
	"tb_action_user_log": "jsonb",
	"tb_ext_user_mapper": "uuid",
	"chat_threads_turns": "four enums (sibc)",
	"tb_stats_menu_visit_log": "interval",
	"tb_activity_user_log": "numeric and a naive timestamp watermark",
}

MAX_ROWS = 5000


def bounded_extractor(source, target, watermark, source_system="iccoli"):
	return build_extractor(
		source, source_system=source_system, target=target, watermark_manager=StubWatermarkManager(watermark)
	)


def newest_watermark(source, extractor, target):
	with source.cursor() as cursor:
		cursor.execute(
			f'SELECT max({extractor.watermark_expr}) FROM "{target["schema_name"]}"."{target["table_name"]}"'
		)
		return cursor.fetchone()[0]


def small_slice(source, target, table_name, newest, source_system="iccoli"):
	"""Walk the lower bound up until the slice is small enough to compare row by row."""
	window = timedelta(days=1)
	for _ in range(6):
		extractor = bounded_extractor(source, target, newest - window, source_system)
		plan = extractor.plan()
		with source.cursor() as cursor:
			cursor.execute(f"SELECT count(*) FROM ({plan.query}) probe", plan.params)
			if cursor.fetchone()[0] <= MAX_ROWS:
				return bounded_extractor(source, target, newest - window, source_system)
		window = window / 10
	return bounded_extractor(source, target, newest - window, source_system)


def check_table(source, dw, table_name, source_system="iccoli"):
	target = next(t for t in get_extraction_targets(source_system) if t["table_name"] == table_name)
	# the staging comparison below reads the whole table, so it must start empty
	reset_staging(dw, source_system, target["schema_name"], table_name)
	if target["load_type"] == "full_refresh":
		# always read whole; only small reference tables are declared this way
		extractor = bounded_extractor(source, target, None, source_system)
	else:
		probe = bounded_extractor(source, target, None, source_system)
		newest = newest_watermark(source, probe, target)
		if newest is None:
			return None  # empty table, nothing to prove
		extractor = small_slice(source, target, table_name, newest, source_system)
	with extractor.extract() as result:
		StagingLoader(dw).load(result)
		source_table = result.source_table
		columns = source_table.quoted_columns
		order = ", ".join(f'"{name}"' for name in source_table.primary_key)

		with source.cursor() as cursor:
			cursor.execute(f"SELECT {columns} FROM ({result.plan.query}) x ORDER BY {order}", result.plan.params)
			source_rows = cursor.fetchall()
		with dw.cursor() as cursor:
			cursor.execute(f'SELECT {columns} FROM stg_{source_system}."{table_name}" ORDER BY {order}')
			staging_rows = cursor.fetchall()

		assert source_rows == staging_rows, f"{table_name}: staging differs from the source"
		return len(source_rows)


def test_jsonb_survives_the_round_trip():
	with sessions() as (source, dw):
		assert check_table(source, dw, "tb_action_user_log") is not None


def test_uuid_and_enum_columns_survive_the_round_trip():
	with sessions() as (source, dw):
		check_table(source, dw, "tb_ext_user_mapper")  # uuid
	with sessions("sibc") as (source, dw):
		check_table(source, dw, "chat_threads_turns", source_system="sibc")  # four enums


def test_interval_survives_the_round_trip():
	with sessions() as (source, dw):
		check_table(source, dw, "tb_stats_menu_visit_log")


def test_numeric_and_naive_timestamps_survive_the_round_trip():
	with sessions() as (source, dw):
		check_table(source, dw, "tb_activity_user_log")


def test_staging_types_match_the_mapping():
	"""Enums land as text; everything else keeps its source type."""
	with sessions() as (source, dw):
		check_table(source, dw, "tb_ext_user_mapper")
		with dw.cursor() as cursor:
			cursor.execute(
				"""SELECT column_name, data_type FROM information_schema.columns
				   WHERE table_schema='stg_iccoli' AND table_name='tb_ext_user_mapper'
				     AND column_name = 'ext_user_uuid'""",
			)
			assert dict(cursor.fetchall())["ext_user_uuid"] == "uuid"

	with sessions("sibc") as (source, dw):
		check_table(source, dw, "chat_threads_turns", source_system="sibc")
		with dw.cursor() as cursor:
			cursor.execute(
				"""SELECT column_name, data_type FROM information_schema.columns
				   WHERE table_schema='stg_sibc' AND table_name='chat_threads_turns'
				     AND column_name IN ('event_type','user_intent')""",
			)
			types = dict(cursor.fetchall())

		assert types["event_type"] == "text"
		assert types["user_intent"] == "text"

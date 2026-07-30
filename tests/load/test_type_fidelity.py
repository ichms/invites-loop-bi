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
from tests.db import sessions
from tests.fakes import StubWatermarkManager

#: table -> the type it is here to prove
CASES = {
	"tb_action_user_log": "jsonb",
	"tb_ext_user_preinfo": "uuid and two enums",
	"tb_stats_menu_visit_log": "interval",
	"tb_activity_user_log": "numeric and a naive timestamp watermark",
}

MAX_ROWS = 5000


def bounded_extractor(source, target, watermark):
	return build_extractor(
		source, source_system="iccoli", target=target, watermark_manager=StubWatermarkManager(watermark)
	)


def newest_watermark(source, extractor, table_name):
	with source.cursor() as cursor:
		cursor.execute(f'SELECT max({extractor.watermark_expr}) FROM "public"."{table_name}"')
		return cursor.fetchone()[0]


def small_slice(source, target, table_name, newest):
	"""Walk the lower bound up until the slice is small enough to compare row by row."""
	window = timedelta(days=1)
	for _ in range(6):
		extractor = bounded_extractor(source, target, newest - window)
		plan = extractor.plan()
		with source.cursor() as cursor:
			cursor.execute(f"SELECT count(*) FROM ({plan.query}) probe", plan.params)
			if cursor.fetchone()[0] <= MAX_ROWS:
				return bounded_extractor(source, target, newest - window)
		window = window / 10
	return bounded_extractor(source, target, newest - window)


def check_table(source, dw, table_name):
	target = next(t for t in get_extraction_targets("iccoli") if t["table_name"] == table_name)
	probe = bounded_extractor(source, target, None)
	newest = newest_watermark(source, probe, table_name)
	if newest is None:
		return None  # empty table, nothing to prove

	extractor = small_slice(source, target, table_name, newest)
	with extractor.extract() as result:
		StagingLoader(dw).load(result)
		source_table = result.source_table
		columns = source_table.quoted_columns
		order = ", ".join(f'"{name}"' for name in source_table.primary_key)

		with source.cursor() as cursor:
			cursor.execute(f"SELECT {columns} FROM ({result.plan.query}) x ORDER BY {order}", result.plan.params)
			source_rows = cursor.fetchall()
		with dw.cursor() as cursor:
			cursor.execute(f'SELECT {columns} FROM stg_iccoli."{table_name}" ORDER BY {order}')
			staging_rows = cursor.fetchall()

		assert source_rows == staging_rows, f"{table_name}: staging differs from the source"
		return len(source_rows)


def test_jsonb_survives_the_round_trip():
	with sessions() as (source, dw):
		assert check_table(source, dw, "tb_action_user_log") is not None


def test_uuid_and_enum_columns_survive_the_round_trip():
	with sessions() as (source, dw):
		check_table(source, dw, "tb_ext_user_preinfo")


def test_interval_survives_the_round_trip():
	with sessions() as (source, dw):
		check_table(source, dw, "tb_stats_menu_visit_log")


def test_numeric_and_naive_timestamps_survive_the_round_trip():
	with sessions() as (source, dw):
		check_table(source, dw, "tb_activity_user_log")


def test_staging_types_match_the_mapping():
	"""Enums land as text; everything else keeps its source type."""
	with sessions() as (source, dw):
		check_table(source, dw, "tb_ext_user_preinfo")
		with dw.cursor() as cursor:
			cursor.execute(
				"""SELECT column_name, data_type FROM information_schema.columns
				   WHERE table_schema='stg_iccoli' AND table_name='tb_ext_user_preinfo'
				     AND column_name IN ('ext_user_uuid','relation_cd','status_cd')""",
			)
			types = dict(cursor.fetchall())

		assert types["ext_user_uuid"] == "uuid"
		assert types["relation_cd"] == "text"
		assert types["status_cd"] == "text"

"""
Real extract -> load round trips.

Everything runs inside a transaction that `tests.db.dw_session` rolls back, so
the warehouse is untouched. Requires access to the iccoli source and the
warehouse; skipped otherwise.
"""

from invites_loop_bi.config import get_extraction_targets
from invites_loop_bi.extract import build_extractor
from invites_loop_bi.extract.introspect import TableSchema
from invites_loop_bi.extract.watermark import WatermarkManager
from invites_loop_bi.load import StagingLoader
from tests.db import sessions
from tests.fakes import StubWatermarkManager

TABLE = "tb_action_mapper"  # small reference table, no personal data, composite key


def target_for(table_name=TABLE, **overrides):
	target = next(t for t in get_extraction_targets("iccoli") if t["table_name"] == table_name)
	return {**target, **overrides}


def staging_count(dw, table_name=TABLE, schema="stg_iccoli"):
	with dw.cursor() as cursor:
		cursor.execute(f'SELECT count(*) FROM {schema}."{table_name}"')
		return cursor.fetchone()[0]


def test_first_run_creates_staging_and_loads_every_row():
	with sessions() as (source, dw):
		loader = StagingLoader(dw)
		extractor = build_extractor(
			source, source_system="iccoli", target=target_for(), watermark_manager=StubWatermarkManager()
		)
		with extractor.extract() as result:
			stats = loader.load(result)

		assert stats.created_table
		assert stats.rows_copied == stats.rows_loaded == result.row_count
		assert staging_count(dw) == result.row_count
		assert stats.observed_watermark is not None, "watermark must come from the loaded rows"


def test_reloading_the_same_rows_upserts_instead_of_duplicating():
	with sessions() as (source, dw):
		loader = StagingLoader(dw)

		def full_load():
			extractor = build_extractor(
				source, source_system="iccoli", target=target_for(), watermark_manager=StubWatermarkManager()
			)
			with extractor.extract() as result:
				return loader.load(result)

		first = full_load()
		after_first = staging_count(dw)
		second = full_load()

		assert not second.created_table
		assert second.rows_loaded == first.rows_loaded
		assert staging_count(dw) == after_first, "the upsert duplicated rows"


def test_loaded_rows_are_identical_to_the_source():
	with sessions() as (source, dw):
		extractor = build_extractor(
			source, source_system="iccoli", target=target_for(), watermark_manager=StubWatermarkManager()
		)
		with extractor.extract() as result:
			StagingLoader(dw).load(result)
			columns = result.source_table.quoted_columns
			order = ", ".join(f'"{name}"' for name in result.source_table.primary_key)

		with source.cursor() as cursor:
			cursor.execute(f'SELECT {columns} FROM public."{TABLE}" ORDER BY {order}')
			source_rows = cursor.fetchall()
		with dw.cursor() as cursor:
			cursor.execute(f'SELECT {columns} FROM stg_iccoli."{TABLE}" ORDER BY {order}')
			staging_rows = cursor.fetchall()

		assert source_rows == staging_rows


def test_full_refresh_truncates_before_loading():
	with sessions() as (source, dw):
		loader = StagingLoader(dw)
		extractor = build_extractor(
			source,
			source_system="iccoli",
			target=target_for(load_type="full_refresh"),
			watermark_manager=StubWatermarkManager(),
		)
		with extractor.extract() as result:
			stats = loader.load(result)

		assert stats.truncated
		assert stats.observed_watermark is None, "a full refresh has no watermark column to read"
		assert staging_count(dw) == result.row_count

		# a second pass must leave the same number of rows, not double them
		extractor2 = build_extractor(
			source,
			source_system="iccoli",
			target=target_for(load_type="full_refresh"),
			watermark_manager=StubWatermarkManager(),
		)
		with extractor2.extract() as result2:
			loader.load(result2)
		assert staging_count(dw) == result2.row_count


def test_a_column_added_upstream_is_added_to_staging():
	"""Simulates source drift by creating staging one column short."""
	with sessions() as (source, dw):
		loader = StagingLoader(dw)
		extractor = build_extractor(
			source, source_system="iccoli", target=target_for(), watermark_manager=StubWatermarkManager()
		)
		with extractor.extract() as result:
			full = result.source_table
			missing = full.columns[-1]
			assert missing.name not in full.primary_key

			stale = TableSchema(
				schema_name=full.schema_name,
				table_name=full.table_name,
				columns=full.columns[:-1],
				primary_key=full.primary_key,
			)
			with dw.cursor() as cursor:
				cursor.execute(loader._create_table_sql(stale, f'stg_iccoli."{TABLE}"'))

			stats = loader.load(result)

		assert stats.added_columns == (missing.name,)
		assert not stats.created_table
		assert staging_count(dw) == result.row_count


def test_watermark_is_committed_only_after_the_load():
	with sessions() as (source, dw):
		watermarks = WatermarkManager(meta_db_conn=dw)
		loader = StagingLoader(dw)
		extractor = build_extractor(
			source, source_system="iccoli", target=target_for(), watermark_manager=watermarks
		)

		assert watermarks.get_last_watermark("iccoli", "public", TABLE) is None

		with extractor.extract() as result:
			stats = loader.load(result)
			extractor.commit(result, stats.observed_watermark, stats.rows_loaded)

		stored = watermarks.get_last_watermark("iccoli", "public", TABLE)
		assert stored == stats.observed_watermark

		with dw.cursor() as cursor:
			cursor.execute(
				"SELECT last_status, row_count FROM stg_meta.watermarks "
				"WHERE source_system='iccoli' AND table_name=%s",
				(TABLE,),
			)
			assert cursor.fetchone() == ("SUCCESS", stats.rows_loaded)


def test_a_failed_run_leaves_the_watermark_alone():
	with sessions() as (source, dw):
		watermarks = WatermarkManager(meta_db_conn=dw)
		loader = StagingLoader(dw)
		extractor = build_extractor(
			source, source_system="iccoli", target=target_for(), watermark_manager=watermarks
		)

		with extractor.extract() as result:
			stats = loader.load(result)
			extractor.commit(result, stats.observed_watermark, stats.rows_loaded)
		good = watermarks.get_last_watermark("iccoli", "public", TABLE)

		extractor.mark_failed(RuntimeError("copy interrupted"))

		# the next run must resume from the last good watermark, not reload everything
		assert watermarks.get_last_watermark("iccoli", "public", TABLE) == good
		with dw.cursor() as cursor:
			cursor.execute(
				"SELECT last_status, last_error FROM stg_meta.watermarks WHERE table_name=%s",
				(TABLE,),
			)
			status, error = cursor.fetchone()
		assert status == "FAILED"
		assert "copy interrupted" in error


KEYLESS_TABLE = "disc_lifelog_user_sleep_detail"  # one of the 14 sources with no primary key


def test_a_keyless_table_replays_without_duplicating():
	"""
	No primary key means no upsert, so the loader clears the window it is about to
	insert. Running the same window twice must leave the same rows behind.
	"""
	from datetime import timedelta

	with sessions("discovery") as (source, dw):
		target = next(t for t in get_extraction_targets("discovery") if t["table_name"] == KEYLESS_TABLE)
		loader = StagingLoader(dw)

		with source.cursor() as cursor:
			cursor.execute(f'SELECT max(measure_end_dt) FROM discovery."{KEYLESS_TABLE}"')
			newest = cursor.fetchone()[0]
		assert newest is not None, "table is empty, nothing to prove"

		def run(watermark):
			extractor = build_extractor(
				source, source_system="discovery", target=target, watermark_manager=StubWatermarkManager(watermark)
			)
			with extractor.extract() as result:
				assert result.source_table.primary_key == (), "this test needs a keyless table"
				return loader.load(result), result.row_count

		# a window small enough to compare, but not empty
		for hours in (6, 24, 24 * 7, 24 * 90):
			watermark = newest - timedelta(hours=hours)
			first, extracted = run(watermark)
			if extracted:
				break
		assert extracted, "no recent rows to exercise the keyless path"

		after_first = staging_count(dw, KEYLESS_TABLE, schema="stg_discovery")
		assert after_first == extracted

		second, extracted_again = run(watermark)
		after_second = staging_count(dw, KEYLESS_TABLE, schema="stg_discovery")

		assert after_second == after_first, "the keyless replay duplicated rows"
		assert second.rows_deleted == extracted_again, "the window should have been cleared before insert"
		assert not second.truncated


def test_an_excluded_column_never_reaches_staging():
	"""
	disc_lifelog_user_meal.meal_data is 557 kB of base64 image per row. It must not
	be read, and the staging table must not have the column at all.
	"""
	from datetime import timedelta

	table = "disc_lifelog_user_meal"
	with sessions("discovery") as (source, dw):
		target = next(t for t in get_extraction_targets("discovery") if t["table_name"] == table)
		assert target["exclude_columns"] == ("meal_data",)

		with source.cursor() as cursor:
			cursor.execute(f'SELECT max(COALESCE(upd_dt, ins_dt)) FROM discovery."{table}"')
			newest = cursor.fetchone()[0]

		extractor = build_extractor(
			source,
			source_system="discovery",
			target=target,
			watermark_manager=StubWatermarkManager(newest - timedelta(days=30)),
		)
		with extractor.extract() as result:
			assert "meal_data" not in result.plan.query
			assert "meal_data" not in result.source_table.column_names
			stats = StagingLoader(dw).load(result)
			extracted = result.row_count

		with dw.cursor() as cursor:
			cursor.execute(
				"""SELECT column_name FROM information_schema.columns
				   WHERE table_schema='stg_discovery' AND table_name=%s""",
				(table,),
			)
			staged = {row[0] for row in cursor.fetchall()}

		assert staged == {"user_lifelog_sn", "ins_dt", "upd_dt", "is_deleted", "_loaded_at"}
		assert "meal_data" not in staged
		assert stats.rows_loaded == extracted

		# the whole point: the slice is tiny without the payload column
		if extracted:
			assert result.byte_count / extracted < 1024, "rows should be tens of bytes, not hundreds of kB"


def test_second_run_after_a_commit_reads_only_what_moved():
	with sessions() as (source, dw):
		watermarks = WatermarkManager(meta_db_conn=dw)
		loader = StagingLoader(dw)

		first = build_extractor(source, source_system="iccoli", target=target_for(), watermark_manager=watermarks)
		with first.extract() as result:
			stats = loader.load(result)
			first.commit(result, stats.observed_watermark, stats.rows_loaded)
		loaded = staging_count(dw)

		second = build_extractor(source, source_system="iccoli", target=target_for(), watermark_manager=watermarks)
		with second.extract() as result2:
			assert not result2.plan.is_full_load
			assert result2.row_count == 0, "nothing changed upstream, so nothing should be re-read"
			stats2 = loader.load(result2)

		assert stats2.rows_loaded == 0
		assert staging_count(dw) == loaded

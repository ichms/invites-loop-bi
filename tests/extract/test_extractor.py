"""Query planning, COPY statement shape and watermark policy."""

from datetime import datetime, timedelta, timezone

from invites_loop_bi.config import get_extraction_targets
from invites_loop_bi.extract import (
	FullRefreshExtractor,
	IncrementalExtractor,
	build_extractor,
	build_extractors,
)
from tests.db import source_session
from tests.fakes import RecordingConnection, StubWatermarkManager, table_schema

WATERMARK = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def make_extractor(watermark=None, *, fallback="create_datetime", overlap=timedelta(0), row_filter=None):
	"""An extractor with its catalog lookup pre-filled, so it needs no database."""
	extractor = IncrementalExtractor(
		source_conn=None,
		source_system="iccoli",
		schema_name="public",
		table_name="tb_demo",
		watermark_col="update_datetime",
		fallback_watermark_col=fallback,
		overlap=overlap,
		row_filter=row_filter,
		watermark_manager=StubWatermarkManager(watermark),
	)
	extractor._source_table = table_schema()
	return extractor


# ----------------------------------------------------------------- offline


def test_first_run_reads_the_whole_table():
	"""No watermark yet -> no predicate at all, so NULL watermarks come along too."""
	plan = make_extractor(watermark=None).plan()
	assert "WHERE" not in plan.query
	assert plan.params == ()
	assert plan.is_full_load


def test_first_run_selects_columns_explicitly_not_star():
	plan = make_extractor(watermark=None).plan()
	assert "SELECT *" not in plan.query
	assert '"user_no", "payload"' in plan.query


def test_second_run_reads_only_what_moved():
	plan = make_extractor(watermark=WATERMARK).plan()
	assert 'COALESCE("update_datetime", "create_datetime") > %s' in plan.query
	assert plan.params == (WATERMARK,)
	assert not plan.is_full_load


def test_fallback_is_omitted_when_not_declared():
	extractor = make_extractor(watermark=WATERMARK, fallback=None)
	assert extractor.watermark_expr == '"update_datetime"'
	assert "COALESCE" not in extractor.plan().query


def test_overlap_widens_the_lower_bound():
	plan = make_extractor(watermark=WATERMARK, overlap=timedelta(minutes=5)).plan()
	assert plan.params == (WATERMARK - timedelta(minutes=5),)


def test_upper_bound_is_optional_and_additive():
	upper = datetime(2026, 2, 1, tzinfo=timezone.utc)
	plan = make_extractor(watermark=WATERMARK).plan(upper_bound=upper)
	assert plan.query.count("%s") == 2
	assert plan.params == (WATERMARK, upper)
	assert plan.upper_bound == upper


def test_excluded_columns_never_reach_the_query():
	"""
	Goes through describe() rather than pre-filling the cache, because that is
	where the exclusion is applied.
	"""
	from invites_loop_bi.extract import extractor as extractor_module

	extractor = IncrementalExtractor(
		source_conn=None,
		source_system="discovery",
		schema_name="discovery",
		table_name="tb_demo",
		watermark_col="update_datetime",
		fallback_watermark_col="create_datetime",
		exclude_columns=("payload",),
		watermark_manager=StubWatermarkManager(),
	)

	original = extractor_module.describe_table
	extractor_module.describe_table = lambda conn, schema, table: table_schema()
	try:
		plan = extractor.plan()
	finally:
		extractor_module.describe_table = original

	assert '"payload"' not in plan.query
	assert "payload" not in plan.source_table.column_names
	# the loader builds its DDL from this same schema, so staging never gets it
	assert '"status_cd"' in plan.query


FILTER = "user_no IN (SELECT user_no FROM public.tb_ext_user_mapper WHERE ext_system_code = 'LOOP')"


def test_row_filter_applies_on_the_first_run_too():
	"""A filtered table is *never* read whole -- that is the point of the filter."""
	plan = make_extractor(watermark=None, row_filter=FILTER).plan()
	assert f"WHERE ({FILTER})" in plan.query
	assert plan.params == ()
	assert plan.is_full_load


def test_row_filter_stays_out_of_the_replayed_predicate():
	"""
	The loader replays `plan.predicate` against *staging* to delete the window it
	is about to insert (tables without a primary key). A row filter's source-local
	references (the mapper subquery) would not resolve there, so the filter must
	live in the query but never in the predicate.
	"""
	plan = make_extractor(watermark=WATERMARK, row_filter=FILTER).plan()
	assert f"({FILTER})" in plan.query
	assert 'COALESCE("update_datetime", "create_datetime") > %s' in plan.query
	assert FILTER not in plan.predicate
	assert plan.params == (WATERMARK,)


def test_row_filter_applies_to_full_refresh():
	extractor = FullRefreshExtractor(
		source_conn=None,
		source_system="iccoli",
		schema_name="public",
		table_name="tb_demo",
		row_filter=FILTER,
		watermark_manager=StubWatermarkManager(),
	)
	extractor._source_table = table_schema()
	plan = extractor.plan()
	assert f"WHERE ({FILTER})" in plan.query
	assert plan.predicate is None


def test_row_filter_with_placeholders_is_rejected():
	"""The COPY query goes through mogrify(), so a stray % corrupts the binding."""
	for bad in ("user_no = %s", "note LIKE 'a%'"):
		try:
			make_extractor(row_filter=bad)
		except ValueError as exc:
			assert "row_filter" in str(exc)
		else:
			raise AssertionError(f"row_filter {bad!r} should raise")
	# a doubled %% is the documented escape and passes
	make_extractor(row_filter="note LIKE 'a%%'")


def test_builder_passes_the_row_filter_from_the_config():
	extractor = build_extractor(
		None,
		target={
			"schema_name": "public",
			"table_name": "tb_user_info",
			"watermark_col": "update_datetime",
			"row_filter": FILTER,
		},
		watermark_manager=StubWatermarkManager(),
	)
	assert extractor.row_filter == FILTER


def test_a_watermark_column_cannot_be_excluded():
	"""The incremental predicate reads it, so this has to fail loudly."""
	for excluded in (("update_datetime",), ("create_datetime",)):
		try:
			IncrementalExtractor(
				source_conn=None,
				source_system="discovery",
				schema_name="discovery",
				table_name="tb_demo",
				watermark_col="update_datetime",
				fallback_watermark_col="create_datetime",
				exclude_columns=excluded,
				watermark_manager=StubWatermarkManager(),
			)
		except ValueError as exc:
			assert "cannot exclude" in str(exc)
		else:
			raise AssertionError(f"excluding {excluded} should raise")


def test_builder_passes_exclusions_from_the_config():
	extractor = build_extractor(
		None,
		target={
			"schema_name": "discovery",
			"table_name": "disc_lifelog_user_meal",
			"watermark_col": "upd_dt",
			"exclude_columns": ("meal_data",),
		},
		watermark_manager=StubWatermarkManager(),
	)
	assert extractor.exclude_columns == ("meal_data",)


def test_unknown_watermark_column_fails_before_running_sql():
	extractor = make_extractor(watermark=WATERMARK)
	extractor.watermark_col = "no_such_column"
	try:
		extractor.plan()
	except KeyError as exc:
		assert "no_such_column" in str(exc)
	else:
		raise AssertionError("a watermark column missing from the source should raise")


def test_full_refresh_has_no_predicate_and_no_watermark_expression():
	extractor = FullRefreshExtractor(
		source_conn=None,
		source_system="ichms",
		schema_name="ichms",
		table_name="com_code",
		watermark_manager=StubWatermarkManager(),
	)
	extractor._source_table = table_schema(table_name="com_code", schema_name="ichms")
	plan = extractor.plan()
	assert "WHERE" not in plan.query
	assert plan.watermark_expr is None
	assert plan.params == ()


def test_copy_statement_wraps_the_query():
	extractor = make_extractor(watermark=None)
	plan = extractor.plan()
	copy_sql = extractor._copy_out_sql(cursor=None, plan=plan)
	assert copy_sql.startswith("COPY (")
	assert copy_sql.endswith(") TO STDOUT WITH (FORMAT csv)")


def test_copy_statement_binds_bounds_through_the_driver():
	"""copy_expert() takes no parameters, so bounds go through mogrify()."""

	class FakeCursor:
		def mogrify(self, query, params):
			assert params == (WATERMARK,)
			return query.replace("%s", "'2026-01-01T12:00:00+00:00'::timestamptz").encode()

	extractor = make_extractor(watermark=WATERMARK)
	copy_sql = extractor._copy_out_sql(FakeCursor(), extractor.plan())
	assert "%s" not in copy_sql
	assert "'2026-01-01T12:00:00+00:00'::timestamptz" in copy_sql


def test_watermark_advances_to_what_was_loaded():
	extractor = make_extractor(watermark=WATERMARK)
	plan = extractor.plan()
	observed = datetime(2026, 3, 1, tzinfo=timezone.utc)
	assert extractor._next_watermark(plan, observed, extracted_at=WATERMARK) == observed


def test_watermark_stays_put_when_nothing_was_loaded():
	extractor = make_extractor(watermark=WATERMARK)
	plan = extractor.plan()
	assert extractor._next_watermark(plan, None, extracted_at=WATERMARK) is None


def test_first_run_with_no_usable_watermark_anchors_on_the_source_clock():
	"""Otherwise a table whose watermarks are all NULL would full-load forever."""
	extractor = make_extractor(watermark=None)
	plan = extractor.plan()
	clock = datetime(2026, 5, 5, tzinfo=timezone.utc)
	assert extractor._next_watermark(plan, None, extracted_at=clock) == clock


def test_full_refresh_records_the_run_time_as_its_watermark():
	extractor = FullRefreshExtractor(
		source_conn=None,
		source_system="ichms",
		schema_name="ichms",
		table_name="com_code",
		watermark_manager=StubWatermarkManager(),
	)
	extractor._source_table = table_schema(table_name="com_code", schema_name="ichms")
	clock = datetime(2026, 5, 5, tzinfo=timezone.utc)
	assert extractor._next_watermark(extractor.plan(), None, extracted_at=clock) == clock


def test_builder_picks_the_strategy_from_the_config():
	incremental = build_extractor(
		None,
		target={"schema_name": "public", "table_name": "t", "watermark_col": "u"},
		watermark_manager=StubWatermarkManager(),
	)
	full = build_extractor(
		None,
		target={"schema_name": "public", "table_name": "t", "load_type": "full_refresh"},
		watermark_manager=StubWatermarkManager(),
	)
	assert isinstance(incremental, IncrementalExtractor)
	assert isinstance(full, FullRefreshExtractor)


def test_builder_rejects_an_unknown_load_type():
	try:
		build_extractor(
			None,
			target={"schema_name": "public", "table_name": "t", "load_type": "sideways"},
			watermark_manager=StubWatermarkManager(),
		)
	except ValueError as exc:
		assert "sideways" in str(exc)
	else:
		raise AssertionError("an unknown load_type should raise")


def test_incremental_without_watermark_column_is_rejected():
	try:
		IncrementalExtractor(
			source_conn=None,
			source_system="iccoli",
			schema_name="public",
			table_name="t",
			watermark_col="",
			watermark_manager=StubWatermarkManager(),
		)
	except ValueError as exc:
		assert "watermark_col" in str(exc)
	else:
		raise AssertionError("an incremental extractor needs a watermark column")


def test_extractor_needs_somewhere_to_keep_watermarks():
	try:
		IncrementalExtractor(source_conn=None, watermark_col="u", table_name="t", schema_name="s")
	except ValueError as exc:
		assert "watermark_manager" in str(exc)
	else:
		raise AssertionError("neither meta_conn nor watermark_manager should be rejected")


# --------------------------------------------------------------------- db


def test_real_first_run_copies_every_row():
	target = next(t for t in get_extraction_targets("iccoli") if t["table_name"] == "tb_action_mapper")
	with source_session() as source:
		extractor = build_extractor(
			source, source_system="iccoli", target=target, watermark_manager=StubWatermarkManager()
		)
		with extractor.extract() as result:
			with source.cursor() as cursor:
				cursor.execute("SELECT count(*) FROM public.tb_action_mapper")
				expected = cursor.fetchone()[0]
			assert result.row_count == expected
			assert result.byte_count > 0
			# one CSV line per row, and the buffer is rewound ready for the loader
			assert len(result.csv.read().decode().splitlines()) == expected


def test_real_incremental_run_copies_a_subset():
	target = next(t for t in get_extraction_targets("iccoli") if t["table_name"] == "tb_action_mapper")
	with source_session() as source:
		full = build_extractor(source, source_system="iccoli", target=target, watermark_manager=StubWatermarkManager())
		with full.extract() as everything:
			total = everything.row_count

		with source.cursor() as cursor:
			cursor.execute("SELECT max(create_datetime) FROM public.tb_action_mapper")
			newest = cursor.fetchone()[0]

		bounded = build_extractor(
			source, source_system="iccoli", target=target, watermark_manager=StubWatermarkManager(newest)
		)
		with bounded.extract() as recent:
			assert recent.row_count == 0, "nothing is newer than the newest row"
			assert recent.row_count < total


def test_real_extract_columns_match_the_catalog_order():
	target = next(t for t in get_extraction_targets("iccoli") if t["table_name"] == "tb_action_mapper")
	with source_session() as source:
		extractor = build_extractor(
			source, source_system="iccoli", target=target, watermark_manager=StubWatermarkManager()
		)
		plan = extractor.plan()
		assert plan.source_table.quoted_columns in plan.query


def test_build_extractors_creates_one_per_target_and_shares_one_manager():
	"""One shared WatermarkManager means the metadata bootstrap runs once, not 18 times."""
	meta = RecordingConnection()
	extractors = build_extractors(None, meta, "iccoli")

	assert len(extractors) == len(get_extraction_targets("iccoli"))
	assert len({id(extractor.wm_manager) for extractor in extractors}) == 1
	bootstraps = [sql for sql in meta.statements() if "CREATE TABLE IF NOT EXISTS stg_meta.watermarks" in sql]
	assert len(bootstraps) == 1

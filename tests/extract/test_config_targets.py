"""The target registry: normalisation, validation and deduplication."""

from invites_loop_bi.config import (
	EXTRACTION_TARGETS,
	FULL_REFRESH_TARGETS,
	LOAD_TYPE_FULL_REFRESH,
	LOAD_TYPE_INCREMENTAL,
	SOURCE_SYSTEMS,
	_normalise,
	get_all_extraction_targets,
	get_extraction_targets,
)

REQUIRED_KEYS = {
	"source_system",
	"schema_name",
	"table_name",
	"load_type",
	"watermark_col",
	"fallback_watermark_col",
	"exclude_columns",
	"row_filter",
	"lookback_days",
}


def test_every_target_has_the_normalised_shape():
	for system in SOURCE_SYSTEMS:
		targets = get_extraction_targets(system)
		assert targets, f"{system} declares no targets"
		for target in targets:
			assert set(target) == REQUIRED_KEYS, target
			assert target["source_system"] == system
			assert target["load_type"] in (LOAD_TYPE_INCREMENTAL, LOAD_TYPE_FULL_REFRESH)


def test_incremental_targets_declare_a_watermark_column():
	for system in SOURCE_SYSTEMS:
		for target in get_extraction_targets(system):
			if target["load_type"] == LOAD_TYPE_INCREMENTAL:
				assert target["watermark_col"], target


def test_full_refresh_targets_declare_no_watermark():
	for system in SOURCE_SYSTEMS:
		for target in get_extraction_targets(system):
			if target["load_type"] == LOAD_TYPE_FULL_REFRESH:
				assert target["watermark_col"] is None, target


def test_no_table_is_declared_twice():
	"""A table can only carry one watermark, so duplicates must be collapsed."""
	for system in SOURCE_SYSTEMS:
		keys = [(t["schema_name"], t["table_name"]) for t in get_extraction_targets(system)]
		assert len(keys) == len(set(keys)), f"{system} still yields duplicates"


def test_a_duplicate_declaration_is_collapsed_to_the_first():
	"""
	The config is clean today, so the dedup path is exercised with an injected
	duplicate -- it is the guard against a table silently carrying two watermarks.
	"""
	original = EXTRACTION_TARGETS["iccoli"]
	duplicate = {**original[0], "watermark_col": "create_datetime"}
	EXTRACTION_TARGETS["iccoli"] = [*original, duplicate]
	try:
		targets = get_extraction_targets("iccoli", include_full_refresh=False)
		keys = [(t["schema_name"], t["table_name"]) for t in targets]
		assert len(keys) == len(set(keys)), "the duplicate was not collapsed"
		assert len(targets) == len(original)
		kept = next(t for t in targets if t["table_name"] == original[0]["table_name"])
		assert kept["watermark_col"] == original[0]["watermark_col"], "the first declaration must win"
	finally:
		EXTRACTION_TARGETS["iccoli"] = original


def test_counts_add_up():
	for system in SOURCE_SYSTEMS:
		incremental = get_extraction_targets(system, include_full_refresh=False)
		full_refresh = get_extraction_targets(system, include_incremental=False)
		combined = get_extraction_targets(system)
		assert len(full_refresh) == len(FULL_REFRESH_TARGETS.get(system, []))
		assert {t["table_name"] for t in combined} == {
			*{t["table_name"] for t in incremental},
			*{t["table_name"] for t in full_refresh},
		}


def test_iccoli_declares_fallback_only_where_updates_can_be_null():
	targets = {t["table_name"]: t for t in get_extraction_targets("iccoli")}
	# update_datetime stays NULL until a row is updated -> needs create_datetime
	assert targets["tb_user_info"]["fallback_watermark_col"] == "create_datetime"
	# an append-only log has nothing to fall back to
	assert targets["tb_user_login_log"]["fallback_watermark_col"] is None


def test_exclusions_default_to_empty_and_are_tuples():
	for system in SOURCE_SYSTEMS:
		for target in get_extraction_targets(system):
			assert isinstance(target["exclude_columns"], tuple)


def test_the_meal_payload_column_is_excluded():
	"""21 GB of base64 images that the dietary history does not need."""
	targets = {t["table_name"]: t for t in get_extraction_targets("discovery")}
	meal = targets["disc_lifelog_user_meal"]
	assert meal["exclude_columns"] == ("meal_data",)
	# edits and soft deletes only show up in upd_dt, which is NULL until they happen
	assert meal["watermark_col"] == "upd_dt"
	assert meal["fallback_watermark_col"] == "ins_dt"


def test_iccoli_user_keyed_tables_are_filtered_to_the_loop_cohort():
	"""
	Community app users never leave the source system (owner decision 2026-08-06,
	IMPLEMENTATION_PLAN.md N-02). Every user_no-keyed iccoli target must carry the
	cohort row filter; the mapper itself is the one deliberate exception.
	"""
	from invites_loop_bi.config.iccoli_targets import LOOP_USERS_ONLY

	targets = {t["table_name"]: t for t in get_extraction_targets("iccoli")}
	user_keyed = {
		"tb_user_login_log",
		"tb_user_personal_info",
		"tb_user_info",
		"tb_activity_user_log",
		"tb_action_user_log",
		"tb_loop_push_history",
		"tb_message_send_hist",
		"tb_stats_avg_login_cnt_log",
		"tb_user_activity_info",
		"tb_user_attendance",
		"tb_user_device_info",
		"tb_stats_menu_visit_log",
		"tb_point_item_srch_hist_log",
		"tb_point_user_dtl",
		"tb_point_user_adj_hist",
	}
	for table in user_keyed:
		assert targets[table]["row_filter"] == LOOP_USERS_ONLY, table
	assert targets["tb_ext_user_mapper"]["row_filter"] is None
	# everything else defaults to unfiltered
	for system in SOURCE_SYSTEMS:
		if system == "iccoli":
			continue
		for target in get_extraction_targets(system):
			assert target["row_filter"] is None, target


def test_iccoli_identity_columns_never_leave_the_source():
	"""N-01: direct identifiers are excluded at extraction, not just at transform."""
	targets = {t["table_name"]: t for t in get_extraction_targets("iccoli")}
	assert "tb_ext_user_preinfo" not in targets, "pre-registration identity must not be a target"
	personal = set(targets["tb_user_personal_info"]["exclude_columns"])
	assert {"ci", "di", "name", "phone", "email", "telecom"} <= personal
	assert "birth" not in personal, "birth stays: it is the single source of birth_year (D-23)"
	device = set(targets["tb_user_device_info"]["exclude_columns"])
	assert {"device_token", "game_token", "apns_push_to_start_token", "apns_la_token"} <= device


def test_the_lifelog_transaction_table_is_extracted_without_its_raw_payload():
	"""
	disc_lifelog_user_info is a target, but never with `lifelog_raw_data`.

	This test used to assert the opposite -- that the table is not extracted at
	all, on the grounds that it is 23 GB and "covered by the per-measurement
	tables". Half of that was wrong: every per-measurement table keys on
	`user_lifelog_sn` and carries no user_id, so without this parent not one
	measurement can be attributed to a user (found 2026-08-06 building
	fct_measurement). The other half was really about one column -- excluding
	`lifelog_raw_data` takes the table from 23 GB to 18 MiB.

	So the guard now protects the property that actually matters: the linkage
	comes in, the payload stays out.
	"""
	targets = {t["table_name"]: t for t in get_extraction_targets("discovery")}
	assert "disc_lifelog_user_info" in targets, "fct_measurement cannot attribute readings without it"
	assert "lifelog_raw_data" in set(targets["disc_lifelog_user_info"]["exclude_columns"]), (
		"lifelog_raw_data is the entire 23 GB; it is redundant with the typed child tables"
	)


def test_the_wearable_streams_re_read_a_backfill_window():
	"""
	Wearables backdate: a watch that has not synced for a fortnight uploads samples
	stamped a fortnight ago, which land *below* the watermark where
	`measured_dt > last_watermark` can never see them again. Measured 2026-08-10:
	454 step rows arrived after a full read, reaching 29 days back, and the
	warehouse was short 4 users on step / 3 on activity / 2 on heartrate / 1 on
	sleep against the source at an identical cutoff.

	Losing these is silent -- every grain and not_null test still passes -- so the
	guard lives here rather than in dbt.
	"""
	from invites_loop_bi.config.discovery_targets import WEARABLE_BACKFILL_LOOKBACK_DAYS

	targets = {t["table_name"]: t for t in get_extraction_targets("discovery")}
	for table in (
		"disc_lifelog_user_step",
		"disc_lifelog_user_activity",
		"disc_lifelog_user_sleep",
		"disc_lifelog_user_oxygen_saturation",
	):
		assert targets[table]["lookback_days"] == WEARABLE_BACKFILL_LOOKBACK_DAYS, table

	# Heartrate is left out ON PURPOSE: 8.5M rows, no usable index on measured_dt,
	# and step is a strict superset of the wearable user set, so it recovers no
	# user the others miss. If a mart ever needs heartrate intensity rather than
	# presence, this assertion is the thing to revisit -- not to silently delete.
	assert targets["disc_lifelog_user_heartrate"]["lookback_days"] is None


def test_meal_needs_no_lookback_because_it_watermarks_on_arrival():
	"""
	The counter-example that scopes the defect. Meal watermarks on
	COALESCE(upd_dt, ins_dt) -- when the row *arrived*, not when the meal was
	eaten -- so a backdated record still comes in above the watermark. It
	reconciled exactly (335 of 335 recorders) in the same audit that found the
	wearable drift. Only measurement-time watermarks need a lookback.
	"""
	targets = {t["table_name"]: t for t in get_extraction_targets("discovery")}
	assert targets["disc_lifelog_user_meal"]["lookback_days"] is None
	assert targets["disc_lifelog_user_meal"]["watermark_col"] == "upd_dt"
	assert targets["disc_lifelog_user_meal"]["fallback_watermark_col"] == "ins_dt"


def test_lookback_defaults_to_none_and_rejects_nonsense():
	assert _normalise("irs", {"schema_name": "s", "table_name": "t", "watermark_col": "w"}, LOAD_TYPE_INCREMENTAL)[
		"lookback_days"
	] is None

	for bad in (-1, "30", True):
		try:
			_normalise(
				"irs",
				{"schema_name": "s", "table_name": "t", "watermark_col": "w", "lookback_days": bad},
				LOAD_TYPE_INCREMENTAL,
			)
		except ValueError as exc:
			assert "lookback_days" in str(exc)
		else:
			raise AssertionError(f"lookback_days={bad!r} should raise")


def test_full_refresh_with_a_lookback_raises():
	"""A full refresh already re-reads everything; a lookback there is a config slip."""
	try:
		_normalise(
			"irs",
			{"schema_name": "s", "table_name": "t", "load_type": LOAD_TYPE_FULL_REFRESH, "lookback_days": 30},
			LOAD_TYPE_FULL_REFRESH,
		)
	except ValueError as exc:
		assert "lookback_days" in str(exc)
	else:
		raise AssertionError("full_refresh + lookback_days should raise")


def test_unknown_source_system_raises():
	try:
		get_extraction_targets("nope")
	except KeyError as exc:
		assert "nope" in str(exc)
	else:
		raise AssertionError("unknown source system should raise")


def test_incremental_target_without_watermark_col_raises():
	try:
		_normalise("iccoli", {"schema_name": "public", "table_name": "x"}, LOAD_TYPE_INCREMENTAL)
	except ValueError as exc:
		assert "watermark_col" in str(exc)
	else:
		raise AssertionError("missing watermark_col should raise")


def test_target_without_table_name_raises():
	try:
		_normalise("iccoli", {"schema_name": "public"}, LOAD_TYPE_FULL_REFRESH)
	except ValueError as exc:
		assert "table_name" in str(exc)
	else:
		raise AssertionError("missing table_name should raise")


def test_get_all_covers_every_system():
	everything = get_all_extraction_targets()
	assert set(everything) == set(SOURCE_SYSTEMS)
	assert sum(len(v) for v in everything.values()) > 100

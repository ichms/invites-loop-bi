#: How far below the watermark the wearable streams are re-read on every run.
#:
#: These tables watermark on the *measurement* time, and a wearable backfills:
#: a watch that has not synced for a fortnight uploads samples stamped a
#: fortnight ago. Such a row lands below the last watermark, where a plain
#: `measured_dt > last_watermark` predicate can never see it -- silent,
#: permanent loss rather than lag. None of these source tables carries an insert
#: timestamp to watermark on instead (checked 2026-08-10), so a lookback window
#: is the only mechanism available.
#:
#: 30 days is measured, not guessed. `disc_lifelog_user_step` got a single full
#: read on 2026-08-06, giving a clean baseline: 454 rows for dates on or before
#: that load arrived *after* it, reaching 29 days back and decaying with age
#: (75 on the load date, ~12-15/day across three weeks, 1-3 at 26-29 days).
#: Re-measure before trusting this number if the sync behaviour changes.
#:
#: Contrast `disc_lifelog_user_meal`, which watermarks on COALESCE(upd_dt,
#: ins_dt) -- an arrival time -- and needs no lookback. It reconciled exactly
#: (335 of 335 recorders) in the same audit that found the wearable drift.
WEARABLE_BACKFILL_LOOKBACK_DAYS = 30

DISCOVERY_EXTRACTION_TARGETS = [
	{
		"schema_name": "discovery",
		"table_name": "disc_consultation_user_info",
		"watermark_col": "consultation_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_disease_detail_info",
		"watermark_col": "updated_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_dtc_user_info",
		"watermark_col": "created_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_genomic_user_info",
		"watermark_col": "created_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_health_user_info",
		"watermark_col": "upd_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_irs_user_info",
		"watermark_col": "created_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_lifelog_user_activity",
		"watermark_col": "measured_dt",
		"fallback_watermark_col": None,
		"lookback_days": WEARABLE_BACKFILL_LOOKBACK_DAYS,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_lifelog_user_bloodglucose",
		"watermark_col": "measured_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_lifelog_user_bloodpressure",
		"watermark_col": "measured_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_lifelog_user_body_info",
		"watermark_col": "measured_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_lifelog_user_bodyfat",
		"watermark_col": "measured_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_lifelog_user_food",
		# No measured_dt on this table; ins_dt is its only timestamp, as in
		# disc_lifelog_user_meal.
		"watermark_col": "ins_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_lifelog_user_grip_strength",
		"watermark_col": "measured_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_lifelog_user_heartrate",
		"watermark_col": "measured_dt",
		"fallback_watermark_col": None,
		# NO lookback, deliberately -- this is the one wearable stream left out.
		# It has the same backdating exposure as its four siblings, but it is
		# 8.5M rows with no usable index on measured_dt (only a composite), so
		# every run already seq-scans it and a 30-day re-read would add real cost
		# to each one. It buys nothing analytically: step is a strict superset of
		# the wearable user set (181 of 181 users, measured 2026-08-10), so
		# heartrate contributes no user the lookback on step would not recover.
		# Revisit if a mart ever needs heartrate *intensity* rather than presence,
		# or if the source gains an index -- see WEARABLE_BACKFILL_LOOKBACK_DAYS.
	},
	{
		# The lifelog parent. Every per-measurement table below keys on
		# `user_lifelog_sn` and carries NO user_id, so without this table not one
		# landed measurement can be attributed to a user -- fct_measurement is
		# impossible without it (found 2026-08-06 while building Phase 3).
		#
		# It was previously skipped for size (23 GB, ~206 kB/row), but the weight
		# is entirely `lifelog_raw_data`; excluding that one column leaves ~60
		# bytes of columns that matter -- the user linkage, the device/platform
		# codes and the measurement location. Same trade already made for
		# disc_lifelog_user_meal's base64 images. The typed child tables carry
		# the readings themselves, so the raw payload is redundant as well as
		# huge.
		"schema_name": "discovery",
		"table_name": "disc_lifelog_user_info",
		"watermark_col": "ins_dt",
		"fallback_watermark_col": None,
		"exclude_columns": ("lifelog_raw_data",),
		# THE PARENT. Every per-measurement lifelog table keys on user_lifelog_sn
		# and carries no user of its own, so this table is the only thing that
		# turns a measurement into a user. Load a child ahead of it and those rows
		# attribute to nobody and vanish from every user-keyed count -- silently,
		# because a row with an unmatched user_lifelog_sn is dropped by an inner
		# join rather than flagged.
		#
		# NEVER run a lifelog child on its own with `--table`. Doing exactly that
		# on 2026-08-10 (four wearable streams refreshed to 08-10 against a parent
		# frozen at 08-06) orphaned 4,651 step rows and took the wearable user
		# count DOWN from 181 to 169 while the row count went UP. It is invisible
		# to every dbt test; only a source-vs-warehouse count catches it.
		#
		# Late-arriving samples are the reason: a watch syncing on the 8th opens a
		# NEW session row here for a measurement stamped the 15th of last month, so
		# a lookback on the children implies a fresh parent. A whole-system run is
		# safe -- the parent's window is a superset of any child's -- but if you
		# touch one child by hand, run this immediately after.
	},
	{
		# Same gap: a per-measurement table that was never a target.
		"schema_name": "discovery",
		"table_name": "disc_lifelog_user_step",
		"watermark_col": "measured_dt",
		"fallback_watermark_col": None,
		"lookback_days": WEARABLE_BACKFILL_LOOKBACK_DAYS,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_lifelog_user_meal",
		# Only the history of dietary records is needed, not the meals themselves:
		# meal_data holds base64 images averaging 557 kB per row, against 44 bytes
		# for every other column combined (21 GB -> ~1.5 MB).
		"exclude_columns": ("meal_data",),
		# upd_dt is NULL until a record is edited or soft-deleted (35,174 of 36,338
		# rows), so the predicate has to fall back to ins_dt -- watermarking on
		# ins_dt alone would never see an edit or a deletion.
		"watermark_col": "upd_dt",
		"fallback_watermark_col": "ins_dt",
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_lifelog_user_oxygen_saturation",
		"watermark_col": "measured_dt",
		"fallback_watermark_col": None,
		"lookback_days": WEARABLE_BACKFILL_LOOKBACK_DAYS,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_lifelog_user_sleep",
		"watermark_col": "total_measure_end_dt",
		"fallback_watermark_col": None,
		"lookback_days": WEARABLE_BACKFILL_LOOKBACK_DAYS,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_lifelog_user_sleep_detail",
		# Wearables write measure_start_dt and measure_end_dt together and both are
		# NOT NULL, so either works and a fallback would never fire.
		"watermark_col": "measure_end_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_lifestyle_survey_question_detail",
		"watermark_col": "updated_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_lifestyle_survey_question_option",
		"watermark_col": "updated_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_lifestyle_user_survey_answer",
		"watermark_col": "updated_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_medical_user_info",
		"watermark_col": "measured_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_prescription_medicine_user_info",
		"watermark_col": "measured_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_survey_discovery_version",
		"watermark_col": "updated_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_user_disease_history",
		"watermark_col": "answered_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_user_race_info_history",
		"watermark_col": "answered_dt",
		"fallback_watermark_col": None,
	},
]


DISCOVERY_FULL_REFRESH_TARGETS = [
	{
		"schema_name": "discovery",
		"table_name": "disc_examination_user_info",
		"load_type": "full_refresh",
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_globalization_code",
		"load_type": "full_refresh",
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_health_info_meta",
		"load_type": "full_refresh",
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_health_info_meta_detail",
		"load_type": "full_refresh",
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_race_info_meta_info",
		"load_type": "full_refresh",
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_user_disease_answer",
		"load_type": "full_refresh",
	},
]

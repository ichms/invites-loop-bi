# Only Loop-cohort app accounts leave the source system; community users' rows
# never reach the warehouse (owner decision 2026-08-06 -- IMPLEMENTATION_PLAN.md
# N-02, consent scope). Applied to every user-keyed table below.
#
# Backfill caveat: a user who enrols *later* gains a mapper row, but their rows
# older than the table's watermark were filtered out while they were still a
# community user and will not be re-read on their own. After an enrolment wave,
# delete the iccoli rows from `stg_meta.watermarks` to force a full re-read --
# loads are idempotent, so the replay is safe and, at these volumes, cheap.
LOOP_USERS_ONLY = "user_no IN (SELECT user_no FROM public.tb_ext_user_mapper WHERE ext_system_code = 'LOOP')"

ICCOLI_EXTRACTION_TARGETS = [
	{
		"schema_name": "public",
		"table_name": "tb_user_login_log",
		"watermark_col": "login_datetime",
		"fallback_watermark_col": None,
		"row_filter": LOOP_USERS_ONLY,
	},
	{
		# Identity table: the columns that make it one stay in the source system
		# (IMPLEMENTATION_PLAN.md N-01). `birth` is retained as the single source
		# of `birth_year` (D-23); dbt staging reduces it and never exposes it raw.
		"schema_name": "public",
		"table_name": "tb_user_personal_info",
		"watermark_col": "update_datetime",
		"fallback_watermark_col": "create_datetime",
		"row_filter": LOOP_USERS_ONLY,
		"exclude_columns": ("ci", "di", "name", "phone", "email", "telecom"),
	},
	{
		"schema_name": "public",
		"table_name": "tb_user_info",
		"watermark_col": "update_datetime",
		"fallback_watermark_col": "create_datetime",
		"row_filter": LOOP_USERS_ONLY,
	},
	{
		"schema_name": "public",
		"table_name": "tb_action_info",
		"watermark_col": "create_datetime",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "public",
		"table_name": "tb_action_mapper",
		"watermark_col": "create_datetime",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "public",
		"table_name": "tb_activity_user_log",
		"watermark_col": "create_datetime",
		"fallback_watermark_col": None,
		"row_filter": LOOP_USERS_ONLY,
	},
	{
		"schema_name": "public",
		"table_name": "tb_action_user_log",
		"watermark_col": "action_datetime",
		"fallback_watermark_col": None,
		"row_filter": LOOP_USERS_ONLY,
	},
	{
		"schema_name": "public",
		"table_name": "tb_loop_push_history",
		# This table has no update_datetime; read_datetime is what changes after
		# insert (when the user opens the push), so it plays the same role.
		"watermark_col": "read_datetime",
		"fallback_watermark_col": "create_datetime",
		"row_filter": LOOP_USERS_ONLY,
	},
	{
		"schema_name": "public",
		"table_name": "tb_message_send_hist",
		"watermark_col": "create_datetime",
		"fallback_watermark_col": None,
		"row_filter": LOOP_USERS_ONLY,
	},
	{
		"schema_name": "public",
		"table_name": "tb_stats_active_user_cnt",
		"watermark_col": "create_datetime",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "public",
		"table_name": "tb_stats_avg_login_cnt_log",
		"watermark_col": "create_datetime",
		"fallback_watermark_col": None,
		"row_filter": LOOP_USERS_ONLY,
	},
	{
		"schema_name": "public",
		"table_name": "tb_user_activity_info",
		"watermark_col": "update_datetime",
		"fallback_watermark_col": "create_datetime",
		"row_filter": LOOP_USERS_ONLY,
	},
	{
		"schema_name": "public",
		"table_name": "tb_user_attendance",
		"watermark_col": "create_datetime",
		"fallback_watermark_col": None,
		"row_filter": LOOP_USERS_ONLY,
	},
	{
		# Engagement facts need the app/OS columns; the push and device
		# identifiers are dropped at the source (N-01).
		"schema_name": "public",
		"table_name": "tb_user_device_info",
		"watermark_col": "update_datetime",
		"fallback_watermark_col": "create_datetime",
		"row_filter": LOOP_USERS_ONLY,
		"exclude_columns": (
			"device_token",
			"game_token",
			"apns_push_to_start_token",
			"apns_la_token",
			"la_activity_id",
			"device_id",
		),
	},
	{
		"schema_name": "public",
		"table_name": "tb_stats_menu_visit_log",
		"watermark_col": "visit_datetime",
		"fallback_watermark_col": None,
		"row_filter": LOOP_USERS_ONLY,
	},
	{
		"schema_name": "public",
		"table_name": "tb_menu_app",
		"watermark_col": "update_datetime",
		"fallback_watermark_col": "create_datetime",
	},
	# tb_ext_user_mapper lives in ICCOLI_FULL_REFRESH_TARGETS below.
	# tb_ext_user_preinfo is deliberately NOT a target: pre-registration identity
	# (name, phone, birth) with no analytical use (N-01). Do not re-add it.
	# --- point shop / point mission -------------------------------------------
	{
		"schema_name": "public",
		"table_name": "tb_point_item",
		"watermark_col": "update_datetime",
		"fallback_watermark_col": "create_datetime",
	},
	{
		"schema_name": "public",
		"table_name": "tb_point_item_ctg",
		"watermark_col": "update_datetime",
		"fallback_watermark_col": "create_datetime",
	},
	{
		"schema_name": "public",
		"table_name": "tb_point_item_hist",
		"watermark_col": "update_datetime",
		"fallback_watermark_col": "create_datetime",
	},
	{
		"schema_name": "public",
		"table_name": "tb_point_item_cpn",
		"watermark_col": "update_datetime",
		"fallback_watermark_col": "create_datetime",
	},
	# The four *_intr_hist tables below are append only and carry no
	# update_datetime. They do have an `intr_datetime` (when the interaction
	# happened), but create_datetime is the row's own insert time, which is what
	# an incremental cutoff needs.
	{
		"schema_name": "public",
		"table_name": "tb_point_item_intr_hist",
		"watermark_col": "create_datetime",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "public",
		"table_name": "tb_point_item_cpn_issue_intr_hist",
		"watermark_col": "create_datetime",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "public",
		"table_name": "tb_point_item_cpn_cncl_intr_hist",
		"watermark_col": "create_datetime",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "public",
		"table_name": "tb_point_item_cpn_state_intr_hist",
		"watermark_col": "create_datetime",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "public",
		"table_name": "tb_point_item_srch_hist_log",
		# The only timestamp on the table, and half of its primary key.
		"watermark_col": "srch_timestamp",
		"fallback_watermark_col": None,
		"row_filter": LOOP_USERS_ONLY,
	},
	{
		"schema_name": "public",
		"table_name": "tb_point_mission",
		"watermark_col": "update_datetime",
		"fallback_watermark_col": "create_datetime",
	},
	{
		"schema_name": "public",
		"table_name": "tb_point_mission_category",
		"watermark_col": "update_datetime",
		"fallback_watermark_col": "create_datetime",
	},
	{
		"schema_name": "public",
		"table_name": "tb_point_mission_dtl",
		"watermark_col": "update_datetime",
		"fallback_watermark_col": "create_datetime",
	},
	{
		"schema_name": "public",
		"table_name": "tb_point_mission_tag",
		"watermark_col": "update_datetime",
		"fallback_watermark_col": "create_datetime",
	},
	{
		"schema_name": "public",
		"table_name": "tb_point_mission_tag_sub",
		"watermark_col": "update_datetime",
		"fallback_watermark_col": "create_datetime",
	},
	{
		"schema_name": "public",
		"table_name": "tb_point_user_dtl",
		"watermark_col": "update_datetime",
		"fallback_watermark_col": "create_datetime",
		"row_filter": LOOP_USERS_ONLY,
	},
	{
		"schema_name": "public",
		"table_name": "tb_point_user_adj_hist",
		"watermark_col": "create_datetime",
		"fallback_watermark_col": None,
		"row_filter": LOOP_USERS_ONLY,
	},
]

ICCOLI_FULL_REFRESH_TARGETS = [
	{
		# The user_no <-> user_id translation table; deliberately unfiltered.
		# Full refresh, not incremental: mappings can be *deleted* at the source
		# (observed 2026-08-06 -- warehouse held one mapping the source no longer
		# had), and an incremental load would keep such rows forever. At ~450 rows
		# a truncate-and-reload costs nothing and cohort membership stays exact.
		"schema_name": "public",
		"table_name": "tb_ext_user_mapper",
		"load_type": "full_refresh",
	},
	{
		# The goods snapshot behind each tb_point_item_intr_hist row. It carries no
		# timestamp at all -- `reg_date` is a varchar 'YYYYMMDD' with a handful of
		# distinct values, not a per-row event time -- and no primary key, so there
		# is nothing to run an incremental cutoff on. Small enough (~19k rows, 6 MB)
		# to truncate and reload.
		"schema_name": "public",
		"table_name": "tb_point_item_intr_hist_dtl",
		"load_type": "full_refresh",
	},
]
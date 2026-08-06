SIBC_EXTRACTION_TARGETS = [
	{
		"schema_name": "sibc",
		"table_name": "api_logs",
		"watermark_col": "created_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "chat_msgs",
		"watermark_col": "created_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "chat_thread_evts",
		"watermark_col": "created_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "chat_threads",
		"watermark_col": "created_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "chat_threads_batch_state",
		"watermark_col": "created_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "chat_threads_turns",
		"watermark_col": "created_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "daily_routine_activities",
		"watermark_col": "updated_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "daily_routines",
		"watermark_col": "updated_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "health_assistant_msg",
		"watermark_col": "generated_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "insight_texts",
		"watermark_col": "updated_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "insight_texts_history",
		"watermark_col": "updated_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "llm_usage",
		"watermark_col": "ts",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "onboarding_qstn_master",
		"watermark_col": "updated_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "send_messages",
		"watermark_col": "created_at",
		"fallback_watermark_col": None,
	},
	{
		# user_name excluded: direct identifier with no analytical use
		# (owner decision 2026-08-06, PII_INVENTORY.md R-4).
		"schema_name": "sibc",
		"table_name": "target_calorie",
		"watermark_col": "updated_at",
		"fallback_watermark_col": None,
		"exclude_columns": ("user_name",),
	},
	{
		"schema_name": "sibc",
		"table_name": "user_bhv_log",
		"watermark_col": "updated_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "user_checkup_log",
		"watermark_col": "updated_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "user_diet_analysis",
		"watermark_col": "created_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "user_dtc_log",
		"watermark_col": "updated_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "user_event_log",
		"watermark_col": "created_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "user_guardrail",
		"watermark_col": "updated_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "user_intg_log",
		"watermark_col": "updated_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "user_irs_log",
		"watermark_col": "updated_at",
		"fallback_watermark_col": None,
	},
	{
		# Name and full DOB (+birth time) stay in the source (owner decision
		# 2026-08-06, PII_INVENTORY.md R-4). birth_year's single source is
		# iccoli tb_user_personal_info.birth (D-23); the static age/bio_age
		# columns remain but are never selected by dbt staging (D-24/D-25).
		"schema_name": "sibc",
		"table_name": "user_master",
		"watermark_col": "updated_at",
		"fallback_watermark_col": None,
		"exclude_columns": ("user_nm", "birthday", "birthtime"),
	},
	{
		# Frozen legacy table (last write 2026-03-06). The relational user_name
		# column is excluded; name keys embedded in its jsonb payloads were
		# stripped once by scripts/20260806_pii_cleanup_phase1.sql (durable,
		# since nothing writes here any more).
		"schema_name": "sibc",
		"table_name": "user_profiles_log",
		"watermark_col": "updated_at",
		"fallback_watermark_col": None,
		"exclude_columns": ("user_name",),
	},
	{
		"schema_name": "sibc",
		"table_name": "user_routine_fdbk",
		"watermark_col": "updated_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "user_state_log",
		"watermark_col": "created_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "user_unavl_periods",
		"watermark_col": "updated_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "weekly_routine_goal",
		"watermark_col": "updated_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "sibc",
		"table_name": "weekly_routine_plan",
		"watermark_col": "updated_at",
		"fallback_watermark_col": None,
	},
]


SIBC_FULL_REFRESH_TARGETS = [
	{
		# Its only timestamp-ish column, `created_at`, is a character(8) holding
		# 'YYYYMMDD', so an incremental cutoff cannot compare against it
		# ("operator does not exist: character > timestamp with time zone").
		# The first run got away with it -- a first load runs no predicate at all --
		# and every run after that failed. Small enough to truncate and reload.
		"schema_name": "sibc",
		"table_name": "user_signature_type",
		"load_type": "full_refresh",
	},
	{
		"schema_name": "sibc",
		"table_name": "disease_factor",
		"load_type": "full_refresh",
	},
	{
		"schema_name": "sibc",
		"table_name": "disease_info",
		"load_type": "full_refresh",
	},
	{
		"schema_name": "sibc",
		"table_name": "genetic_trait_info",
		"load_type": "full_refresh",
	},
	{
		"schema_name": "sibc",
		"table_name": "lifestyle_mapping",
		"load_type": "full_refresh",
	},
	{
		"schema_name": "sibc",
		"table_name": "signature_type_mapping",
		"load_type": "full_refresh",
	},
]
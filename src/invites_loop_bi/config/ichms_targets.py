# Direct identifiers are excluded at extraction (owner decision 2026-08-06,
# PII_INVENTORY.md R-5): iCHMS is the auth/identity layer, is NOT cohort-
# filtered (~16k accounts), and no mart reads it -- phone numbers, names, birth
# dates, login credentials/IPs and the medical chart number never leave the
# source. scripts/20260806_pii_cleanup_phase1.sql dropped the already-landed
# copies. Whether these tables belong in the warehouse at all remains open.
ICHMS_EXTRACTION_TARGETS = [
	{
		"schema_name": "ichms",
		"table_name": "auth_client",
		"watermark_col": "updated_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "ichms",
		"table_name": "auth_customer",
		"watermark_col": "updated_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "ichms",
		"table_name": "auth_user",
		"watermark_col": "updated_dt",
		"fallback_watermark_col": None,
		"exclude_columns": ("user_tel",),
	},
	{
		"schema_name": "ichms",
		"table_name": "auth_user_account",
		"watermark_col": "updated_dt",
		"fallback_watermark_col": None,
		# login_pw is bcrypt-hashed, but credential material has zero analytical
		# value and does not belong in an analytics warehouse in any form.
		"exclude_columns": ("login_id", "login_pw"),
	},
	{
		"schema_name": "ichms",
		"table_name": "auth_user_customer",
		"watermark_col": "linked_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "ichms",
		"table_name": "auth_user_login_history",
		"watermark_col": "login_dt",
		"fallback_watermark_col": None,
		"exclude_columns": ("login_ip", "token_id"),
	},
	{
		"schema_name": "ichms",
		"table_name": "auth_user_profile",
		"watermark_col": "updated_dt",
		"fallback_watermark_col": None,
		"exclude_columns": ("user_name", "user_birth"),
	},
	{
		"schema_name": "ichms",
		"table_name": "auth_user_withdraw_history",
		"watermark_col": "withdraw_dt",
		"fallback_watermark_col": None,
		"exclude_columns": ("user_tel",),
	},
	{
		"schema_name": "ichms",
		"table_name": "cnet_event_info_transmit_history",
		"watermark_col": "updated_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "ichms",
		"table_name": "cnet_push_info_transmit_history",
		"watermark_col": "updated_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "ichms",
		"table_name": "cudc_workflow_history",
		"watermark_col": "updated_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "ichms",
		"table_name": "mem_family",
		"watermark_col": "upd_dt",
		"fallback_watermark_col": None,
		"exclude_columns": ("family_name",),
	},
	{
		# msg_cn is free-text family messages; the engagement signals
		# (is_like, is_read, send_dt) stay.
		"schema_name": "ichms",
		"table_name": "mem_family_msg",
		"watermark_col": "send_dt",
		"fallback_watermark_col": None,
		"exclude_columns": ("msg_cn",),
	},
	{
		"schema_name": "ichms",
		"table_name": "mem_user",
		"watermark_col": "updated_dt",
		"fallback_watermark_col": None,
		"exclude_columns": ("chart_no", "profile_img_url"),
	},
]

ICHMS_FULL_REFRESH_TARGETS = [
	{
		"schema_name": "ichms",
		"table_name": "com_code",
		"load_type": "full_refresh",
	},
	{
		"schema_name": "ichms",
		"table_name": "com_code_language_map",
		"load_type": "full_refresh",
	},
]
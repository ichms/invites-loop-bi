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
	},
	{
		"schema_name": "ichms",
		"table_name": "auth_user_account",
		"watermark_col": "updated_dt",
		"fallback_watermark_col": None,
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
	},
	{
		"schema_name": "ichms",
		"table_name": "auth_user_profile",
		"watermark_col": "updated_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "ichms",
		"table_name": "auth_user_withdraw_history",
		"watermark_col": "withdraw_dt",
		"fallback_watermark_col": None,
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
		"watermark_col": "updated_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "ichms",
		"table_name": "mem_family",
		"watermark_col": "upd_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "ichms",
		"table_name": "mem_family_msg",
		"watermark_col": "send_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "ichms",
		"table_name": "mem_user",
		"watermark_col": "updated_dt",
		"fallback_watermark_col": None,
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
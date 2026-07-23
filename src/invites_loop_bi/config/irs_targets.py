IRS_EXTRACTION_TARGETS = [
	{
		"schema_name": "irs",
		"table_name": "irs_data",
		"watermark_col": "updated_at",
		"fallback_watermark_col": "created_at",
	},
	{
		"schema_name": "irs",
		"table_name": "irs_data_log",
		"watermark_col": "create_date",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "irs",
		"table_name": "job_input_data",
		"watermark_col": "created_at",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "irs",
		"table_name": "user_irs_hist",
		"watermark_col": "created_at",
		"fallback_watermark_col": None,
	},
]

IRS_FULL_REFRESH_TARGETS = [
	{
		"schema_name": "irs",
		"table_name": "disease_info",
		"load_type": "full_refresh",
	},
]
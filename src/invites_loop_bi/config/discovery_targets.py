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
	},
	# disc_lifelog_user_info is deliberately NOT extracted: it holds every lifelog
	# transaction (23 GB, ~206 kB per row) and the same ground can be covered from
	# the per-measurement tables below.
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
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_lifelog_user_sleep",
		"watermark_col": "total_measure_end_dt",
		"fallback_watermark_col": None,
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

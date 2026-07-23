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
		"watermark_col": "measured_dt",
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
	{
		"schema_name": "discovery",
		"table_name": "disc_lifelog_user_info",
		"watermark_col": "ins_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_lifelog_user_meal",
		"watermark_col": "ins_dt",
		"fallback_watermark_col": None,
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
		"watermark_col": "measure_end_dt",
		"fallback_watermark_col": None,
	},
	{
		"schema_name": "discovery",
		"table_name": "disc_lifelog_user_sleep_detail",
		"watermark_col": "measured_dt",
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

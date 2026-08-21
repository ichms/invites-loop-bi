-- GRAIN: one canonical behavioural channel.
--
-- This is conservative load evidence, not a DAG-run audit. The current EL
-- control table records each target only when its watermark advances (or a full
-- refresh completes); an empty incremental run is invisible. Consequently the
-- model exposes TARGET_SUCCESS_ONLY and subtracts one KST calendar day from the
-- oldest dependency timestamp. P7 must add a run ledger before this can claim
-- DAG_COMPLETE.

with dependencies(channel_code, source_system, schema_name, table_name, load_mode) as (

	values
		('app_login', 'iccoli', 'public', 'tb_user_login_log', 'INCREMENTAL'),
		('app_action', 'iccoli', 'public', 'tb_action_user_log', 'INCREMENTAL'),
		('app_search', 'iccoli', 'public', 'tb_search_log', 'FULL_REFRESH'),
		('share_created', 'iccoli', 'public', 'tb_share_info', 'FULL_REFRESH'),
		('share_interaction', 'iccoli', 'public', 'tb_share_log', 'FULL_REFRESH'),
		('coaching', 'sibc', 'sibc', 'daily_routine_activities', 'INCREMENTAL'),
		('measurement', 'discovery', 'discovery', 'disc_lifelog_user_info', 'INCREMENTAL'),
		('measurement', 'discovery', 'discovery', 'disc_lifelog_user_bloodpressure', 'INCREMENTAL'),
		('measurement', 'discovery', 'discovery', 'disc_lifelog_user_body_info', 'INCREMENTAL'),
		('measurement', 'discovery', 'discovery', 'disc_lifelog_user_bodyfat', 'INCREMENTAL'),
		('measurement', 'discovery', 'discovery', 'disc_lifelog_user_grip_strength', 'INCREMENTAL'),
		('measurement', 'discovery', 'discovery', 'disc_lifelog_user_bloodglucose', 'INCREMENTAL'),
		('meal', 'discovery', 'discovery', 'disc_lifelog_user_info', 'INCREMENTAL'),
		('meal', 'discovery', 'discovery', 'disc_lifelog_user_meal', 'INCREMENTAL'),
		('wearable', 'discovery', 'discovery', 'disc_lifelog_user_info', 'INCREMENTAL'),
		('wearable', 'discovery', 'discovery', 'disc_lifelog_user_step', 'INCREMENTAL'),
		('wearable', 'discovery', 'discovery', 'disc_lifelog_user_activity', 'INCREMENTAL'),
		('wearable', 'discovery', 'discovery', 'disc_lifelog_user_heartrate', 'INCREMENTAL'),
		('wearable', 'discovery', 'discovery', 'disc_lifelog_user_oxygen_saturation', 'INCREMENTAL'),
		('wearable', 'discovery', 'discovery', 'disc_lifelog_user_sleep', 'INCREMENTAL'),
		('integrated_analysis', 'sibc', 'sibc', 'user_intg_log', 'INCREMENTAL'),
		('irs_score', 'irs', 'irs', 'user_irs_hist', 'INCREMENTAL')

),

watermarks as (

	select
		source_system,
		schema_name,
		table_name,
		last_status,
		updated_at
	from {{ source('stg_meta', 'watermarks') }}

),

dependency_status as (

	select
		d.*,
		w.last_status,
		w.updated_at
	from dependencies as d
	left join watermarks as w
		using (source_system, schema_name, table_name)

),

rolled_up as (

	select
		channel_code,
		count(*)::int as dependency_count,
		count(*) filter (where last_status = 'SUCCESS')::int as successful_dependency_count,
		bool_and(last_status = 'SUCCESS' and updated_at is not null) as all_dependencies_successful,
		min(updated_at) as oldest_recorded_success_at,
		max(updated_at) as latest_recorded_success_at,
		bool_or(load_mode = 'INCREMENTAL') as has_empty_incremental_run_blind_spot
	from dependency_status
	group by 1

),

observed_frontiers as (

	select 'app_login'::text as channel_code, max(login_date) as observed_event_through_date from {{ ref('fct_app_login_event') }}
	union all select 'app_action', max(action_date) from {{ ref('fct_app_action') }}
	union all select 'app_search', max(search_date) from {{ ref('fct_app_search_event') }}
	union all select 'share_created', max(share_created_date) from {{ ref('fct_share_link') }}
	union all select 'share_interaction', max(interaction_date) from {{ ref('fct_share_interaction_event') }}
	union all select 'coaching', max(ymd_date) from {{ ref('fct_coaching_event') }}
	union all select 'measurement', max(measured_date) from {{ ref('fct_measurement') }}
	union all select 'meal', max(recorded_date) from {{ ref('fct_meal_event') }}
	union all select 'wearable', max(ymd_date) from {{ ref('fct_wearable_day') }}
	union all select 'integrated_analysis', max(ymd_date) from {{ ref('fct_user_intg_analysis_day') }}
	union all select 'irs_score', max(ymd_date) from {{ ref('fct_user_disease_day') }}

)

select
	r.channel_code,
	r.dependency_count,
	r.successful_dependency_count,
	r.all_dependencies_successful,
	r.oldest_recorded_success_at,
	r.latest_recorded_success_at,
	case
		when r.all_dependencies_successful
			then (r.oldest_recorded_success_at at time zone 'Asia/Seoul')::date - 1
	end as load_complete_through_date,
	o.observed_event_through_date,
	r.has_empty_incremental_run_blind_spot,
	'TARGET_SUCCESS_ONLY'::text as completion_evidence_kind
from rolled_up as r
left join observed_frontiers as o using (channel_code)

-- Every canonical fact row for a cohort user must survive the dense panel.
-- This includes all app/share channels, coaching, measurements, meals,
-- wearable streams, integrated analysis, and per-disease IRS rows.

with expected as (
	select 'app_login_events'::text as channel, count(*)::bigint as total from {{ ref('fct_app_login_event') }}
	union all select 'app_actions', count(*) from {{ ref('fct_app_action') }}
	union all select 'app_search_events', count(*) from {{ ref('fct_app_search_event') }}
	union all select 'share_links_created', count(*) from {{ ref('fct_share_link') }}
	union all select 'share_interaction_events', count(*) from {{ ref('fct_share_interaction_event') }}
	union all select 'routines_delivered', count(*) from {{ ref('fct_coaching_event') }}
	union all select 'routines_completed', count(*) from {{ ref('fct_coaching_event') }} where is_completed
	union all select 'manual_measurements', count(*) from {{ ref('fct_measurement') }}
	union all select 'meal_records', count(*) from {{ ref('fct_meal_event') }}
	union all select 'wearable_streams_active', sum(
		(step_count is not null)::int + (sleep_hours is not null)::int
		+ (activity_hours is not null)::int + (heartrate_mean is not null)::int
		+ (spo2_mean is not null)::int)::bigint from {{ ref('fct_wearable_day') }}
	union all select 'intg_analysis_rows', count(*) from {{ ref('fct_user_intg_analysis_day') }}
	union all select 'diseases_scored', count(*) from {{ ref('fct_user_disease_day') }}
),
actual as (
	select 'app_login_events'::text as channel, sum(app_login_events)::bigint as total from {{ ref('fct_user_day') }}
	union all select 'app_actions', sum(app_actions) from {{ ref('fct_user_day') }}
	union all select 'app_search_events', sum(app_search_events) from {{ ref('fct_user_day') }}
	union all select 'share_links_created', sum(share_links_created) from {{ ref('fct_user_day') }}
	union all select 'share_interaction_events', sum(share_interaction_events) from {{ ref('fct_user_day') }}
	union all select 'routines_delivered', sum(routines_delivered) from {{ ref('fct_user_day') }}
	union all select 'routines_completed', sum(routines_completed) from {{ ref('fct_user_day') }}
	union all select 'manual_measurements', sum(manual_measurements) from {{ ref('fct_user_day') }}
	union all select 'meal_records', sum(meal_records) from {{ ref('fct_user_day') }}
	union all select 'wearable_streams_active', sum(wearable_streams_active) from {{ ref('fct_user_day') }}
	union all select 'intg_analysis_rows', sum(intg_analysis_rows) from {{ ref('fct_user_day') }}
	union all select 'diseases_scored', sum(diseases_scored) from {{ ref('fct_user_day') }}
)
select e.channel, e.total as expected_total, a.total as actual_total
from expected as e
inner join actual as a using (channel)
where e.total is distinct from a.total

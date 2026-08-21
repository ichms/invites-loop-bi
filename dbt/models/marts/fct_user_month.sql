-- GRAIN: one user × calendar month represented in fct_user_day.
-- Calendar and cohort-relative time are carried together. Numerators are
-- paired with observed-day denominators, and boundary truncation is explicit.
-- remote_care_qualifying_days remains NULL because no approved qualifying-day
-- definition or device-allocation source exists yet.

with daily as (
	select * from {{ ref('fct_user_day') }}
),
users as (
	select user_id, joined_dt::date as joined_date from {{ ref('dim_user') }}
),
monthly as (
	select
		d.user_id,
		date_trunc('month', d.ymd_date)::date as month_start_date,
		min(d.ymd_date) as panel_start_date,
		max(d.ymd_date) as panel_end_date,
		count(*)::int as panel_days,
		count(*) filter (where d.app_login_state in ('OBSERVED_ACTIVITY', 'OBSERVED_ZERO'))::int as app_login_observed_days,
		count(*) filter (where d.app_action_state in ('OBSERVED_ACTIVITY', 'OBSERVED_ZERO'))::int as app_action_observed_days,
		count(*) filter (where d.app_search_state in ('OBSERVED_ACTIVITY', 'OBSERVED_ZERO'))::int as app_search_observed_days,
		count(*) filter (where d.share_created_state in ('OBSERVED_ACTIVITY', 'OBSERVED_ZERO'))::int as share_created_observed_days,
		count(*) filter (where d.share_interaction_state in ('OBSERVED_ACTIVITY', 'OBSERVED_ZERO'))::int as share_interaction_observed_days,
		count(*) filter (where d.coaching_state in ('OBSERVED_ACTIVITY', 'OBSERVED_ZERO'))::int as coaching_observed_days,
		sum(d.app_login_events)::bigint as app_login_events,
		sum(d.app_actions)::bigint as app_actions,
		sum(d.app_search_events)::bigint as app_search_events,
		sum(d.share_links_created)::bigint as share_links_created,
		sum(d.share_interaction_events)::bigint as share_interaction_events,
		count(*) filter (where coalesce(d.app_login_events, 0) > 0
			or coalesce(d.app_actions, 0) > 0
			or coalesce(d.app_search_events, 0) > 0
			or coalesce(d.share_links_created, 0) > 0)::int as app_engaged_days,
		sum(d.routines_delivered)::bigint as routines_delivered,
		sum(d.routines_completed)::bigint as routines_completed,
		count(*) filter (where coalesce(d.manual_measurements, 0) > 0)::int as measurement_activity_days,
		sum(d.manual_measurements)::bigint as manual_measurements,
		count(*) filter (where coalesce(d.meal_records, 0) > 0)::int as meal_activity_days,
		sum(d.meal_records)::bigint as meal_records,
		count(*) filter (where coalesce(d.wearable_streams_active, 0) > 0)::int as wearable_activity_days,
		sum(d.wearable_streams_active)::bigint as wearable_streams_active,
		count(*) filter (where d.integrated_analysis_state in ('OBSERVED_ACTIVITY', 'OBSERVED_ZERO'))::int as integrated_analysis_observed_days,
		count(*) filter (where d.irs_score_state in ('OBSERVED_ACTIVITY', 'OBSERVED_ZERO'))::int as irs_score_observed_days,
		sum(d.intg_analysis_rows)::bigint as intg_analysis_rows,
		sum(d.diseases_scored)::bigint as diseases_scored
	from daily as d
	group by 1, 2
)

select
	m.user_id,
	m.month_start_date,
	(m.month_start_date + interval '1 month - 1 day')::date as month_end_date,
	(
		extract(year from age(m.month_start_date, date_trunc('month', u.joined_date)::date)) * 12
		+ extract(month from age(m.month_start_date, date_trunc('month', u.joined_date)::date))
	)::int as cohort_month_index,
	m.panel_start_date,
	m.panel_end_date,
	m.panel_days,
	m.panel_start_date > m.month_start_date as is_left_partial_month,
	m.panel_end_date < (m.month_start_date + interval '1 month - 1 day')::date as is_right_censored,
	(m.panel_start_date > m.month_start_date
		or m.panel_end_date < (m.month_start_date + interval '1 month - 1 day')::date) as is_partial_month,
	m.app_login_observed_days,
	m.app_action_observed_days,
	m.app_search_observed_days,
	m.share_created_observed_days,
	m.share_interaction_observed_days,
	m.coaching_observed_days,
	m.app_login_events,
	m.app_actions,
	m.app_search_events,
	m.share_links_created,
	m.share_interaction_events,
	m.app_engaged_days,
	m.routines_delivered,
	m.routines_completed,
	m.measurement_activity_days,
	m.manual_measurements,
	m.meal_activity_days,
	m.meal_records,
	m.wearable_activity_days,
	m.wearable_streams_active,
	m.integrated_analysis_observed_days,
	m.irs_score_observed_days,
	m.intg_analysis_rows,
	m.diseases_scored,
	null::int as remote_care_qualifying_days,
	'HYPOTHESIS_UNDEFINED'::text as remote_care_qualifying_day_status
from monthly as m
inner join users as u using (user_id)

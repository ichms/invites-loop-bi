-- GRAIN: one user × KST calendar day.
-- Dense does not mean "every missing row is zero". Each channel has its own
-- load frontier and eligibility state. A zero is emitted only when both are
-- established; otherwise the count is NULL and the companion state explains
-- why. The spine never extends to current_date.

with users_base as (
	select user_id, birth_year, joined_dt::date as joined_date,
		app_registered_at::date as app_registered_date
	from {{ ref('dim_user') }}
),

logins as (
	select user_id, login_date as ymd_date, count(*)::int as app_login_events
	from {{ ref('fct_app_login_event') }} group by 1, 2
),
actions as (
	select user_id, action_date as ymd_date, count(*)::int as app_actions
	from {{ ref('fct_app_action') }} group by 1, 2
),
searches as (
	select user_id, search_date as ymd_date, count(*)::int as app_search_events
	from {{ ref('fct_app_search_event') }} group by 1, 2
),
shares_created as (
	select user_id, share_created_date as ymd_date, count(*)::int as share_links_created
	from {{ ref('fct_share_link') }} group by 1, 2
),
share_interactions as (
	-- Neutral downstream interaction. This never makes the mapped sender active.
	select user_id, interaction_date as ymd_date, count(*)::int as share_interaction_events
	from {{ ref('fct_share_interaction_event') }} group by 1, 2
),
coaching as (
	select user_id, ymd_date, count(*)::int as routines_delivered,
		count(*) filter (where is_completed)::int as routines_completed
	from {{ ref('fct_coaching_event') }} group by 1, 2
),
measurements as (
	select user_id, measured_date as ymd_date, count(*)::int as manual_measurements
	from {{ ref('fct_measurement') }} group by 1, 2
),
meals as (
	select user_id, recorded_date as ymd_date, count(*)::int as meal_records
	from {{ ref('fct_meal_event') }} group by 1, 2
),
wearable as (
	select user_id, ymd_date,
		((step_count is not null)::int + (sleep_hours is not null)::int
		+ (activity_hours is not null)::int + (heartrate_mean is not null)::int
		+ (spo2_mean is not null)::int)::int as wearable_streams_active
	from {{ ref('fct_wearable_day') }}
),
intg as (
	select *, 1::int as intg_analysis_rows
	from {{ ref('fct_user_intg_analysis_day') }}
),
scores as (
	select user_id, ymd_date, count(*)::int as diseases_scored,
		count(*) filter (where irs_score is not null)::int as diseases_with_irs_score
	from {{ ref('fct_user_disease_day') }} group by 1, 2
),

app_first as (
	select user_id, min(ymd_date) as first_app_event_date
	from (
		select user_id, ymd_date from logins
		union all select user_id, ymd_date from actions
		union all select user_id, ymd_date from searches
		union all select user_id, ymd_date from shares_created
		union all select user_id, ymd_date from share_interactions
	) as app_events group by 1
),
coaching_first as (
	select user_id, min(ymd_date) as first_coaching_date from coaching group by 1
),
users as (
	select u.*,
		least(u.app_registered_date, af.first_app_event_date) as app_eligible_from_date,
		least(u.joined_date, cf.first_coaching_date) as coaching_eligible_from_date,
		u.joined_date as analysis_eligible_from_date
	from users_base as u
	left join app_first as af using (user_id)
	left join coaching_first as cf using (user_id)
),
activity_bounds as (
	select user_id, min(ymd_date) as first_activity_date
	from (
		select user_id, ymd_date from logins
		union all select user_id, ymd_date from actions
		union all select user_id, ymd_date from searches
		union all select user_id, ymd_date from shares_created
		union all select user_id, ymd_date from share_interactions
		union all select user_id, ymd_date from coaching
		union all select user_id, ymd_date from measurements
		union all select user_id, ymd_date from meals
		union all select user_id, ymd_date from wearable
		union all select user_id, ymd_date from intg
		union all select user_id, ymd_date from scores
	) as all_activity group by 1
),
status as (
	select
		max(load_complete_through_date) filter (where channel_code = 'app_login') as app_login_through,
		max(load_complete_through_date) filter (where channel_code = 'app_action') as app_action_through,
		max(load_complete_through_date) filter (where channel_code = 'app_search') as app_search_through,
		max(load_complete_through_date) filter (where channel_code = 'share_created') as share_created_through,
		max(load_complete_through_date) filter (where channel_code = 'share_interaction') as share_interaction_through,
		max(load_complete_through_date) filter (where channel_code = 'coaching') as coaching_through,
		max(load_complete_through_date) filter (where channel_code = 'measurement') as measurement_through,
		max(load_complete_through_date) filter (where channel_code = 'meal') as meal_through,
		max(load_complete_through_date) filter (where channel_code = 'wearable') as wearable_through,
		max(load_complete_through_date) filter (where channel_code = 'integrated_analysis') as intg_through,
		max(load_complete_through_date) filter (where channel_code = 'irs_score') as irs_through,
		max(greatest(load_complete_through_date, observed_event_through_date)) as panel_through
	from {{ ref('fct_channel_load_status') }}
),
spine as (
	select u.user_id, d.date_day as ymd_date
	from users as u
	left join activity_bounds as ab using (user_id)
	cross join status as st
	inner join {{ ref('dim_date') }} as d
		on d.date_day between least(u.joined_date, coalesce(ab.first_activity_date, u.joined_date))
			and st.panel_through
),
raw as (
	select sp.user_id, sp.ymd_date, u.birth_year, u.joined_date,
		u.app_eligible_from_date, u.coaching_eligible_from_date,
		u.analysis_eligible_from_date, st.*,
		l.app_login_events as raw_app_login_events,
		a.app_actions as raw_app_actions,
		se.app_search_events as raw_app_search_events,
		sc.share_links_created as raw_share_links_created,
		si.share_interaction_events as raw_share_interaction_events,
		c.routines_delivered as raw_routines_delivered,
		c.routines_completed as raw_routines_completed,
		m.manual_measurements as raw_manual_measurements,
		ml.meal_records as raw_meal_records,
		w.wearable_streams_active as raw_wearable_streams_active,
		i.intg_analysis_rows as raw_intg_analysis_rows,
		s.diseases_scored as raw_diseases_scored,
		s.diseases_with_irs_score as raw_diseases_with_irs_score,
		i.signature_description, i.signature_disease_type_code,
		i.signature_disease_type_label, i.signature_lifestyle_type_code,
		i.signature_lifestyle_type_label, i.signature_potential_type_code,
		i.signature_potential_type_label, i.signature_segment_type_code,
		i.signature_segment_type_label
	from spine as sp
	inner join users as u using (user_id)
	cross join status as st
	left join logins as l using (user_id, ymd_date)
	left join actions as a using (user_id, ymd_date)
	left join searches as se using (user_id, ymd_date)
	left join shares_created as sc using (user_id, ymd_date)
	left join share_interactions as si using (user_id, ymd_date)
	left join coaching as c using (user_id, ymd_date)
	left join measurements as m using (user_id, ymd_date)
	left join meals as ml using (user_id, ymd_date)
	left join wearable as w using (user_id, ymd_date)
	left join intg as i using (user_id, ymd_date)
	left join scores as s using (user_id, ymd_date)
)

select
	r.user_id, r.ymd_date,
	case when r.birth_year is not null
		then ((r.ymd_date - make_date(r.birth_year, 7, 1)) / 365.25)::numeric(5, 2) end as age_at_activity,
	case when r.birth_year is not null
		then (floor(((r.ymd_date - make_date(r.birth_year, 7, 1)) / 365.25) / 5) * 5)::int end as age_band_5y,
	(r.ymd_date - r.joined_date)::int as days_since_joined,
	(extract(year from age(r.ymd_date, r.joined_date)) * 12
		+ extract(month from age(r.ymd_date, r.joined_date)))::int as months_since_joined,
	r.signature_description, r.signature_disease_type_code,
	r.signature_disease_type_label, r.signature_lifestyle_type_code,
	r.signature_lifestyle_type_label, r.signature_potential_type_code,
	r.signature_potential_type_label, r.signature_segment_type_code,
	r.signature_segment_type_label,

	case when r.raw_app_login_events is not null then r.raw_app_login_events
		when r.ymd_date <= r.app_login_through and r.ymd_date >= r.app_eligible_from_date then 0 end as app_login_events,
	case when r.raw_app_actions is not null then r.raw_app_actions
		when r.ymd_date <= r.app_action_through and r.ymd_date >= r.app_eligible_from_date then 0 end as app_actions,
	case when r.raw_app_search_events is not null then r.raw_app_search_events
		when r.ymd_date <= r.app_search_through and r.ymd_date >= r.app_eligible_from_date then 0 end as app_search_events,
	case when r.raw_share_links_created is not null then r.raw_share_links_created
		when r.ymd_date <= r.share_created_through and r.ymd_date >= r.app_eligible_from_date then 0 end as share_links_created,
	case when r.raw_share_interaction_events is not null then r.raw_share_interaction_events
		when r.ymd_date <= r.share_interaction_through and r.ymd_date >= r.app_eligible_from_date then 0 end as share_interaction_events,
	case when r.raw_routines_delivered is not null then r.raw_routines_delivered
		when r.ymd_date <= r.coaching_through and r.ymd_date >= r.coaching_eligible_from_date then 0 end as routines_delivered,
	case when r.raw_routines_delivered is not null then r.raw_routines_completed
		when r.ymd_date <= r.coaching_through and r.ymd_date >= r.coaching_eligible_from_date then 0 end as routines_completed,
	-- Device allocation is not sourced. Real rows are observed; absence remains
	-- NULL rather than manufacturing inactivity.
	r.raw_manual_measurements as manual_measurements,
	r.raw_meal_records as meal_records,
	r.raw_wearable_streams_active as wearable_streams_active,
	case when r.raw_intg_analysis_rows is not null then r.raw_intg_analysis_rows
		when r.ymd_date <= r.intg_through and r.ymd_date >= r.analysis_eligible_from_date then 0 end as intg_analysis_rows,
	case when r.raw_diseases_scored is not null then r.raw_diseases_scored
		when r.ymd_date <= r.irs_through and r.ymd_date >= r.analysis_eligible_from_date then 0 end as diseases_scored,
	case when r.raw_diseases_scored is not null then r.raw_diseases_with_irs_score
		when r.ymd_date <= r.irs_through and r.ymd_date >= r.analysis_eligible_from_date then 0 end as diseases_with_irs_score,

	case when r.raw_app_login_events is not null then 'OBSERVED_ACTIVITY'
		when r.app_login_through is null or r.ymd_date > r.app_login_through then 'NOT_LOADED'
		when r.app_eligible_from_date is null then 'ELIGIBILITY_UNKNOWN'
		when r.ymd_date < r.app_eligible_from_date then 'NOT_YET_ELIGIBLE' else 'OBSERVED_ZERO' end as app_login_state,
	case when r.raw_app_actions is not null then 'OBSERVED_ACTIVITY'
		when r.app_action_through is null or r.ymd_date > r.app_action_through then 'NOT_LOADED'
		when r.app_eligible_from_date is null then 'ELIGIBILITY_UNKNOWN'
		when r.ymd_date < r.app_eligible_from_date then 'NOT_YET_ELIGIBLE' else 'OBSERVED_ZERO' end as app_action_state,
	case when r.raw_app_search_events is not null then 'OBSERVED_ACTIVITY'
		when r.app_search_through is null or r.ymd_date > r.app_search_through then 'NOT_LOADED'
		when r.app_eligible_from_date is null then 'ELIGIBILITY_UNKNOWN'
		when r.ymd_date < r.app_eligible_from_date then 'NOT_YET_ELIGIBLE' else 'OBSERVED_ZERO' end as app_search_state,
	case when r.raw_share_links_created is not null then 'OBSERVED_ACTIVITY'
		when r.share_created_through is null or r.ymd_date > r.share_created_through then 'NOT_LOADED'
		when r.app_eligible_from_date is null then 'ELIGIBILITY_UNKNOWN'
		when r.ymd_date < r.app_eligible_from_date then 'NOT_YET_ELIGIBLE' else 'OBSERVED_ZERO' end as share_created_state,
	case when r.raw_share_interaction_events is not null then 'OBSERVED_ACTIVITY'
		when r.share_interaction_through is null or r.ymd_date > r.share_interaction_through then 'NOT_LOADED'
		when r.app_eligible_from_date is null then 'ELIGIBILITY_UNKNOWN'
		when r.ymd_date < r.app_eligible_from_date then 'NOT_YET_ELIGIBLE' else 'OBSERVED_ZERO' end as share_interaction_state,
	case when r.raw_routines_delivered is not null then 'OBSERVED_ACTIVITY'
		when r.coaching_through is null or r.ymd_date > r.coaching_through then 'NOT_LOADED'
		when r.ymd_date < r.coaching_eligible_from_date then 'NOT_YET_ELIGIBLE' else 'OBSERVED_ZERO' end as coaching_state,
	case when r.raw_manual_measurements is not null then 'OBSERVED_ACTIVITY'
		when r.measurement_through is null or r.ymd_date > r.measurement_through then 'NOT_LOADED' else 'ELIGIBILITY_UNKNOWN' end as measurement_state,
	case when r.raw_meal_records is not null then 'OBSERVED_ACTIVITY'
		when r.meal_through is null or r.ymd_date > r.meal_through then 'NOT_LOADED' else 'ELIGIBILITY_UNKNOWN' end as meal_state,
	case when r.raw_wearable_streams_active is not null then 'OBSERVED_ACTIVITY'
		when r.wearable_through is null or r.ymd_date > r.wearable_through then 'NOT_LOADED' else 'ELIGIBILITY_UNKNOWN' end as wearable_state,
	case when r.raw_intg_analysis_rows is not null then 'OBSERVED_ACTIVITY'
		when r.intg_through is null or r.ymd_date > r.intg_through then 'NOT_LOADED'
		when r.ymd_date < r.analysis_eligible_from_date then 'NOT_YET_ELIGIBLE' else 'OBSERVED_ZERO' end as integrated_analysis_state,
	case when r.raw_diseases_scored is not null then 'OBSERVED_ACTIVITY'
		when r.irs_through is null or r.ymd_date > r.irs_through then 'NOT_LOADED'
		when r.ymd_date < r.analysis_eligible_from_date then 'NOT_YET_ELIGIBLE' else 'OBSERVED_ZERO' end as irs_score_state,

	case when r.raw_app_login_events is not null then true
		when r.ymd_date <= r.app_login_through and r.ymd_date >= r.app_eligible_from_date then false end as did_login,
	case when r.raw_wearable_streams_active is not null then true else null end as had_passive_collection,
	r.app_login_through, r.app_action_through, r.app_search_through,
	r.share_created_through, r.share_interaction_through, r.coaching_through,
	r.measurement_through, r.meal_through, r.wearable_through,
	r.intg_through, r.irs_through
from raw as r

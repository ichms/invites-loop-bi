-- GRAIN: one row per activity_row_id — one JITAI activity delivered to one user
-- on one day. Enforced in marts.yml; never cut (D-04).
--
-- Delivery, response and latency in one row, which is what every adherence and
-- responsiveness metric needs:
--   delivered_at        when the activity was created for the user
--   completed_at        when they completed it (NULL = delivered, not completed)
--   is_completed        the flag Superset users will actually filter on
--   response_latency_minutes  completed_at - delivered_at
--
-- Non-completions are kept deliberately — they are the denominator. A fact
-- filtered to completions only would make every adherence rate 100%.
--
-- is_active = false rows are also kept: an activity withdrawn before the user
-- acted on it is a real event with a real reason (inactive_reason_code), and
-- dropping them would silently inflate adherence.

with activities as (

	select
		activity_row_id,
		user_id,
		ymd_date,
		routine_id,
		weekly_goal_id,
		domain,
		category,
		routine_code,
		title,
		activity_no,
		activity_period,
		priority,
		priority_rank,
		provision_type,
		is_active,
		inactive_reason_code,
		is_mood_reflected,
		anchor_window_start,
		anchor_window_end,
		delivered_at,
		completed_at
	from {{ ref('stg_sibc__daily_routine_activities') }}

),

users as (

	select user_id
	from {{ ref('dim_user') }}

)

select
	a.activity_row_id,
	a.user_id,
	a.ymd_date,
	a.routine_id,
	a.weekly_goal_id,
	a.domain,
	a.category,
	a.routine_code,
	a.title,
	a.activity_no,
	a.activity_period,
	a.priority,
	a.priority_rank,
	a.provision_type,
	a.is_active,
	a.inactive_reason_code,
	a.is_mood_reflected,
	a.anchor_window_start,
	a.anchor_window_end,
	a.delivered_at,
	a.completed_at,
	a.completed_at is not null as is_completed,
	case
		when a.completed_at is not null and a.delivered_at is not null
			then (extract(epoch from (a.completed_at - a.delivered_at)) / 60)::numeric(12, 2)
	end as response_latency_minutes
from activities as a
inner join users as u using (user_id)

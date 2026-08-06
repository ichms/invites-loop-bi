-- Grain: one row per activity_row_id — one JITAI activity delivered to one user
-- on one day. Backs fct_coaching_event.
--
-- `completed_at` is the response signal: null means delivered-but-not-completed,
-- which is the denominator of every adherence metric, so non-completions are
-- kept rather than filtered.
--
-- Not selected: activity_details, completion_check_type, completion_answer,
-- anchor_basis (JSONB payloads holding question text and the user's own
-- answers). The scalar signals a coaching metric needs — domain, category,
-- priority, provision type, delivery and completion time — are all columns
-- already. If an answer distribution is ever needed, that is an allow-listed
-- flattening exercise like the sibc logs, not a raw passthrough.

select
	activity_row_id,
	user_id,
	to_date(ymd, 'YYYYMMDD') as ymd_date,
	routine_id,
	assigned_routine_id,
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
	created_at as delivered_at,
	completed_at,
	updated_at
from {{ source('stg_sibc', 'daily_routine_activities') }}

-- GRAIN: one row per action_log_no — one app action by one user. Enforced in
-- marts.yml; never cut (D-04).
--
-- The one fact family that needed the Q-10 key translation, and it is already
-- done: stg_iccoli__tb_action_user_log resolves user_no -> user_id through the
-- mapper inside its CTE, so nothing here ever sees a user_no.
--
-- target_data passes through as jsonb. Its top-level keys are POINT,
-- TAG_USAGE, ACTIVITY and CONTENT (measured 2026-08-06) — operational payloads
-- with no identity content. It is not flattened because no metric needs it yet;
-- when one does, that is an allow-list exercise (D-26), not a `->>` in a
-- dashboard.

with actions as (

	select
		action_log_no,
		user_id,
		action_no,
		target_data,
		action_datetime
	from {{ ref('stg_iccoli__tb_action_user_log') }}

),

users as (

	select user_id
	from {{ ref('dim_user') }}

)

select
	a.action_log_no,
	a.user_id,
	a.action_no,
	a.action_datetime,
	(a.action_datetime at time zone 'Asia/Seoul')::date as action_date,
	a.target_data
from actions as a
inner join users as u using (user_id)

-- Grain: one row per action_log_no. Source of fct_app_action — the one fact
-- family that needs the Q-10 key translation, done here once so no mart ever
-- sees a user_no.
--
-- target_data passes through as jsonb; its top-level keys today are POINT,
-- TAG_USAGE, ACTIVITY and CONTENT (measured 2026-08-06) — no identity content.

with loop_users as (

	select
		user_no,
		ext_user_uuid as user_id
	from {{ source('stg_iccoli', 'tb_ext_user_mapper') }}
	where ext_system_code = 'LOOP'

),

source as (

	select
		action_log_no,
		user_no,
		action_no,
		target_data,
		action_datetime
	from {{ source('stg_iccoli', 'tb_action_user_log') }}

)

select
	s.action_log_no,
	u.user_id,
	s.action_no,
	s.target_data,
	s.action_datetime
from source as s
left join loop_users as u using (user_no)

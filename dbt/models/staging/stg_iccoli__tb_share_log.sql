-- Grain: one row per share_log_no (neutral downstream interaction candidate).
--
-- PII boundary: share_key, recipient serial/IP/user-agent, and raw from_user_no
-- are absent. user_id maps the source from_user actor; it does not prove that
-- the sender actively performed this downstream event.

with loop_users as (

	select
		user_no,
		ext_user_uuid as user_id
	from {{ source('stg_iccoli', 'tb_ext_user_mapper') }}
	where ext_system_code = 'LOOP'

),

source_rows as (

	select
		share_log_no,
		share_no,
		from_user_no,
		point_call_yn,
		create_datetime
	from {{ source('stg_iccoli', 'tb_share_log') }}

)

select
	s.share_log_no,
	s.share_no,
	u.user_id,
	s.create_datetime as interaction_at,
	(s.create_datetime at time zone 'Asia/Seoul')::date as interaction_date,
	s.point_call_yn as source_point_call_yn
from source_rows as s
left join loop_users as u on u.user_no = s.from_user_no

-- Grain: one row per (user_id, login_datetime) in practice; the source has no
-- primary key (one of the 14 known keyless tables), so no unique test is
-- declared — engagement metrics aggregate this anyway.

with loop_users as (

	select
		user_no,
		ext_user_uuid as user_id
	from {{ source('stg_iccoli', 'tb_ext_user_mapper') }}
	where ext_system_code = 'LOOP'

),

source as (

	select
		user_no,
		login_datetime,
		channel_type
	from {{ source('stg_iccoli', 'tb_user_login_log') }}

)

select
	u.user_id,
	s.login_datetime,
	s.channel_type
from source as s
left join loop_users as u using (user_no)

-- Grain: one row per user_id.
--
-- id (login identifier), nickname, sub_nickname and introduce no longer land
-- at all (dropped + excluded at extraction 2026-08-06, PII_INVENTORY.md R-1).
-- invite_code and profile_file_no still land but are not selected here —
-- invite_code joins the invite-mission analysis when a model needs it.

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
		channel_type,
		status,
		last_login_datetime,
		time_zone,
		create_datetime,
		update_datetime,
		deactivated_datetime,
		purged_datetime
	from {{ source('stg_iccoli', 'tb_user_info') }}

)

select
	u.user_id,
	s.channel_type,
	s.status,
	s.last_login_datetime,
	s.time_zone,
	s.create_datetime,
	s.update_datetime,
	s.deactivated_datetime,
	s.purged_datetime
from source as s
left join loop_users as u using (user_no)

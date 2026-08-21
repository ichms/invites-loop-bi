-- Grain: one row per share_no (share link/object creation).
--
-- PII boundary: share_key is excluded before landing. Polymorphic target_no
-- and raw user_no are deliberately omitted from this general staging model.

with loop_users as (

	select
		user_no,
		ext_user_uuid as user_id
	from {{ source('stg_iccoli', 'tb_ext_user_mapper') }}
	where ext_system_code = 'LOOP'

),

source_rows as (

	select
		share_no,
		share_type,
		user_no,
		create_datetime
	from {{ source('stg_iccoli', 'tb_share_info') }}

)

select
	s.share_no,
	u.user_id,
	s.share_type,
	s.create_datetime as share_created_at,
	(s.create_datetime at time zone 'Asia/Seoul')::date as share_created_date
from source_rows as s
left join loop_users as u using (user_no)

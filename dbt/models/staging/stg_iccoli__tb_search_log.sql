-- Grain: one row per search_log_no.
--
-- PII boundary: word is excluded before landing and is not selected here.
-- user_no is used only inside the mapper join and never leaves staging.

with loop_users as (

	select
		user_no,
		ext_user_uuid as user_id
	from {{ source('stg_iccoli', 'tb_ext_user_mapper') }}
	where ext_system_code = 'LOOP'

),

source_rows as (

	select
		search_log_no,
		user_no,
		create_datetime,
		display_yn
	from {{ source('stg_iccoli', 'tb_search_log') }}

)

select
	s.search_log_no,
	u.user_id,
	s.create_datetime as searched_at,
	(s.create_datetime at time zone 'Asia/Seoul')::date as search_date,
	s.display_yn as source_display_yn
from source_rows as s
left join loop_users as u using (user_no)

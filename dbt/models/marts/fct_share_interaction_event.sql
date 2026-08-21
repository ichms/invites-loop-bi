-- GRAIN: one row per share_log_no for an actor in the current SiBC cohort.
--
-- This remains a neutral downstream interaction candidate. The mapped user_id
-- is source from_user_no; do not call the row an open, success, or sender
-- active event until the source write contract is confirmed.

with interactions as (

	select
		share_log_no,
		share_no,
		user_id,
		interaction_at,
		interaction_date,
		source_point_call_yn
	from {{ ref('stg_iccoli__tb_share_log') }}

),

cohort as (

	select user_id
	from {{ ref('dim_user') }}

)

select i.*
from interactions as i
inner join cohort as c using (user_id)

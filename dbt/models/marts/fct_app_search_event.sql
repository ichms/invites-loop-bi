-- GRAIN: one row per search_log_no for an actor in the current SiBC cohort.
--
-- P3 joins the canonical user dimension after removing its lifetime wearable
-- dependencies, so the ordinary fact-to-dimension contract is now explicit.

with events as (

	select
		search_log_no,
		user_id,
		searched_at,
		search_date,
		source_display_yn
	from {{ ref('stg_iccoli__tb_search_log') }}

),

cohort as (

	select user_id
	from {{ ref('dim_user') }}

)

select e.*
from events as e
inner join cohort as c using (user_id)

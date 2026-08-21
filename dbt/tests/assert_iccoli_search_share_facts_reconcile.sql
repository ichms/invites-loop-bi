-- Fact population is the staged Loop actor intersected with the current SiBC
-- cohort. Mapper-only actors remain visible in the staging-to-fact delta; the
-- expected count is recomputed dynamically rather than pinned to a snapshot.

with cohort as (

	select user_id
	from {{ ref('stg_sibc__user_master') }}

),

expected as (

	select 'search'::text as channel, count(*) as row_count
	from {{ ref('stg_iccoli__tb_search_log') }} as e
	inner join cohort as c using (user_id)

	union all

	select 'share_link', count(*)
	from {{ ref('stg_iccoli__tb_share_info') }} as e
	inner join cohort as c using (user_id)

	union all

	select 'share_interaction', count(*)
	from {{ ref('stg_iccoli__tb_share_log') }} as e
	inner join cohort as c using (user_id)

),

actual as (

	select 'search'::text as channel, count(*) as row_count
	from {{ ref('fct_app_search_event') }}

	union all

	select 'share_link', count(*)
	from {{ ref('fct_share_link') }}

	union all

	select 'share_interaction', count(*)
	from {{ ref('fct_share_interaction_event') }}

)

select
	e.channel,
	e.row_count as expected_fact_rows,
	a.row_count as actual_fact_rows
from expected as e
inner join actual as a using (channel)
where e.row_count <> a.row_count

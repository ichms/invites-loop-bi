-- Every P0-minimised landing row must survive P1 staging exactly once. Actor
-- mapping is left-joined so a mapper drift appears as a null user_id and fails
-- both this reconciliation and the model not-null test.

with expected as (

	select 'search'::text as channel, count(*) as row_count
	from {{ source('stg_iccoli', 'tb_search_log') }}

	union all

	select 'share_link', count(*)
	from {{ source('stg_iccoli', 'tb_share_info') }}

	union all

	select 'share_interaction', count(*)
	from {{ source('stg_iccoli', 'tb_share_log') }}

),

actual as (

	select
		'search'::text as channel,
		count(*) as row_count,
		count(*) filter (where user_id is null) as unmapped_rows
	from {{ ref('stg_iccoli__tb_search_log') }}

	union all

	select
		'share_link',
		count(*),
		count(*) filter (where user_id is null)
	from {{ ref('stg_iccoli__tb_share_info') }}

	union all

	select
		'share_interaction',
		count(*),
		count(*) filter (where user_id is null)
	from {{ ref('stg_iccoli__tb_share_log') }}

)

select
	e.channel,
	e.row_count as landing_rows,
	a.row_count as staging_rows,
	a.unmapped_rows
from expected as e
inner join actual as a using (channel)
where e.row_count <> a.row_count
	or a.unmapped_rows <> 0

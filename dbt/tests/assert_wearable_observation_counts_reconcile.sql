-- The facts collapse exact payload duplicates but source_row_count must retain
-- their multiplicity. Reconcile each cohort-filtered fact back to attributable
-- staging observations so neither a join nor dedupe can silently lose rows.

with lifelog as (

	select l.user_lifelog_sn
	from {{ ref('stg_discovery__lifelog_user_info') }} as l
	inner join {{ ref('dim_user') }} as u using (user_id)

),

expected as (

	select 'step' as stream_code, sum(s.source_row_count) as row_count
	from {{ ref('stg_discovery__lifelog_wearable_step') }} as s
	inner join lifelog as l using (user_lifelog_sn)
	union all
	select 'activity', sum(s.source_row_count)
	from {{ ref('stg_discovery__lifelog_wearable_activity') }} as s
	inner join lifelog as l using (user_lifelog_sn)
	union all
	select 'heartrate', sum(s.source_row_count)
	from {{ ref('stg_discovery__lifelog_wearable_heartrate') }} as s
	inner join lifelog as l using (user_lifelog_sn)
	union all
	select 'oxygen_saturation', sum(s.source_row_count)
	from {{ ref('stg_discovery__lifelog_wearable_oxygen_saturation') }} as s
	inner join lifelog as l using (user_lifelog_sn)
	union all
	select 'sleep', sum(s.source_row_count)
	from {{ ref('stg_discovery__lifelog_wearable_sleep') }} as s
	inner join lifelog as l using (user_lifelog_sn)
	union all
	select 'sleep_stage', sum(d.source_row_count)
	from {{ ref('stg_discovery__lifelog_wearable_sleep_stage') }} as d
	inner join {{ ref('stg_discovery__lifelog_wearable_sleep') }} as s using (user_sleep_sn)
	inner join lifelog as l using (user_lifelog_sn)

),

actual as (

	select 'step' as stream_code, sum(source_row_count) as row_count
	from {{ ref('fct_wearable_step') }}
	union all
	select 'activity', sum(source_row_count)
	from {{ ref('fct_wearable_activity') }}
	union all
	select 'heartrate', sum(source_row_count)
	from {{ ref('fct_wearable_heartrate') }}
	union all
	select 'oxygen_saturation', sum(source_row_count)
	from {{ ref('fct_wearable_oxygen_saturation') }}
	union all
	select 'sleep', sum(source_row_count)
	from {{ ref('fct_wearable_sleep') }}
	union all
	select 'sleep_stage', sum(source_row_count)
	from {{ ref('fct_wearable_sleep_stage') }}

)

select
	coalesce(e.stream_code, a.stream_code) as stream_code,
	e.row_count as expected_row_count,
	a.row_count as actual_row_count
from expected as e
full outer join actual as a using (stream_code)
where e.row_count is distinct from a.row_count

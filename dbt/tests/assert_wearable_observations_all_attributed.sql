{{ config(tags=['wearable_detail']) }}

-- Wearable child tables carry no user_id. Direct streams must resolve through
-- the lifelog parent; sleep-stage intervals must first resolve through sleep.
-- A missing parent would otherwise disappear silently from the mart facts.

with direct_observations as (

	select 'step' as stream_code, source_observation_id, user_lifelog_sn
	from {{ ref('stg_discovery__lifelog_wearable_step') }}
	union all
	select 'activity', source_observation_id, user_lifelog_sn
	from {{ ref('stg_discovery__lifelog_wearable_activity') }}
	union all
	select 'heartrate', source_observation_id, user_lifelog_sn
	from {{ ref('stg_discovery__lifelog_wearable_heartrate') }}
	union all
	select 'oxygen_saturation', source_observation_id, user_lifelog_sn
	from {{ ref('stg_discovery__lifelog_wearable_oxygen_saturation') }}
	union all
	select 'sleep', source_observation_id, user_lifelog_sn
	from {{ ref('stg_discovery__lifelog_wearable_sleep') }}

),

unattributed_direct as (

	select d.stream_code, d.source_observation_id
	from direct_observations as d
	left join {{ ref('stg_discovery__lifelog_user_info') }} as l using (user_lifelog_sn)
	where l.user_lifelog_sn is null

),

unattributed_sleep_stage as (

	select 'sleep_stage' as stream_code, d.source_observation_id
	from {{ ref('stg_discovery__lifelog_wearable_sleep_stage') }} as d
	left join {{ ref('stg_discovery__lifelog_wearable_sleep') }} as s using (user_sleep_sn)
	where s.user_sleep_sn is null

)

select * from unattributed_direct
union all
select * from unattributed_sleep_stage

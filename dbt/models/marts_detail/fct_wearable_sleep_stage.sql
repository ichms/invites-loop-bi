-- GRAIN: one row per distinct source sleep-stage interval (observation_id).
-- The detail source has no lifelog key, so attribution runs through its sleep
-- session and then through stg_discovery__lifelog_user_info.

select
	d.source_observation_id as observation_id,
	l.user_id,
	d.started_at,
	d.ended_at,
	(d.started_at at time zone 'Asia/Seoul')::date as started_date,
	extract(epoch from (d.ended_at - d.started_at))::numeric as duration_seconds,
	d.sleep_stage_code,
	d.user_sleep_sn,
	l.device_type_code as device_type_id,
	l.measure_platform_code,
	l.measure_location,
	s.user_lifelog_sn,
	d.source_row_count
from {{ ref('stg_discovery__lifelog_wearable_sleep_stage') }} as d
inner join {{ ref('stg_discovery__lifelog_wearable_sleep') }} as s using (user_sleep_sn)
inner join {{ ref('stg_discovery__lifelog_user_info') }} as l using (user_lifelog_sn)
inner join {{ ref('dim_user') }} as u using (user_id)

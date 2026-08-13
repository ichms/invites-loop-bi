-- GRAIN: one row per distinct source activity observation (observation_id).
-- Activity is an interval; measured_at is the source's observation timestamp.

select
	a.source_observation_id as observation_id,
	l.user_id,
	a.measured_at,
	(a.measured_at at time zone 'Asia/Seoul')::date as measured_date,
	a.started_at,
	a.ended_at,
	extract(epoch from (a.ended_at - a.started_at))::numeric as duration_seconds,
	a.activity_type_code,
	a.kcal_burned,
	a.distance_m,
	l.device_type_code as device_type_id,
	l.measure_platform_code,
	l.measure_location,
	a.user_lifelog_sn,
	a.source_row_count
from {{ ref('stg_discovery__lifelog_wearable_activity') }} as a
inner join {{ ref('stg_discovery__lifelog_user_info') }} as l using (user_lifelog_sn)
inner join {{ ref('dim_user') }} as u using (user_id)

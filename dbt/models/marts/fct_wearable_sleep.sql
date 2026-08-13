-- GRAIN: one row per distinct source sleep session (observation_id).
-- Sessions are dated from their KST start date, matching fct_wearable_day.

select
	s.source_observation_id as observation_id,
	l.user_id,
	s.started_at,
	s.ended_at,
	(s.started_at at time zone 'Asia/Seoul')::date as started_date,
	extract(epoch from (s.ended_at - s.started_at))::numeric as duration_seconds,
	s.user_sleep_sn,
	l.device_type_code as device_type_id,
	l.measure_platform_code,
	l.measure_location,
	s.user_lifelog_sn,
	s.source_row_count
from {{ ref('stg_discovery__lifelog_wearable_sleep') }} as s
inner join {{ ref('stg_discovery__lifelog_user_info') }} as l using (user_lifelog_sn)
inner join {{ ref('dim_user') }} as u using (user_id)

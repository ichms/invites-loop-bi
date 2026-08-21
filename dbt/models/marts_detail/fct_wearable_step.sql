-- GRAIN: one row per distinct source step observation (observation_id).
-- Exact duplicate payloads collapse; source_row_count retains their multiplicity.

select
	s.source_observation_id as observation_id,
	l.user_id,
	s.measured_at,
	(s.measured_at at time zone 'Asia/Seoul')::date as measured_date,
	s.step_count,
	s.kcal_burned,
	s.distance_m,
	l.device_type_code as device_type_id,
	l.measure_platform_code,
	l.measure_location,
	s.user_lifelog_sn,
	s.source_row_count
from {{ ref('stg_discovery__lifelog_wearable_step') }} as s
inner join {{ ref('stg_discovery__lifelog_user_info') }} as l using (user_lifelog_sn)
inner join {{ ref('dim_user') }} as u using (user_id)

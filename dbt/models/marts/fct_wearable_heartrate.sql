-- GRAIN: one row per distinct source heart-rate observation (observation_id).
-- Different values in the same timestamp/type slot remain separate observations.

select
	h.source_observation_id as observation_id,
	l.user_id,
	h.measured_at,
	(h.measured_at at time zone 'Asia/Seoul')::date as measured_date,
	h.heartrate_type_code,
	h.heartrate_count,
	l.device_type_code as device_type_id,
	l.measure_platform_code,
	l.measure_location,
	h.user_lifelog_sn,
	h.source_row_count
from {{ ref('stg_discovery__lifelog_wearable_heartrate') }} as h
inner join {{ ref('stg_discovery__lifelog_user_info') }} as l using (user_lifelog_sn)
inner join {{ ref('dim_user') }} as u using (user_id)

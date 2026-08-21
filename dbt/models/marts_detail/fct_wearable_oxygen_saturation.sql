-- GRAIN: one row per distinct source oxygen-saturation observation
-- (observation_id). user_sleep_sn is retained when the reading belongs to sleep.

select
	o.source_observation_id as observation_id,
	l.user_id,
	o.measured_at,
	(o.measured_at at time zone 'Asia/Seoul')::date as measured_date,
	o.oxygen_saturation,
	o.user_sleep_sn,
	l.device_type_code as device_type_id,
	l.measure_platform_code,
	l.measure_location,
	o.user_lifelog_sn,
	o.source_row_count
from {{ ref('stg_discovery__lifelog_wearable_oxygen_saturation') }} as o
inner join {{ ref('stg_discovery__lifelog_user_info') }} as l using (user_lifelog_sn)
inner join {{ ref('dim_user') }} as u using (user_id)

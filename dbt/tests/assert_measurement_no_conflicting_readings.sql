-- The atomic measurement fact must preserve every distinct observation
-- signature. Same user/time/metric rows are allowed: nine such slots differ by
-- platform in the 2026-08-21 baseline. A failure here means the fact collapsed
-- or altered value, unit, device, platform, or location.

with cohort as (

	select user_id from {{ ref('dim_user') }}

),

expected as (

	select
		l.user_id,
		m.source_stream,
		m.user_lifelog_sn as source_transaction_id,
		m.measured_at,
		m.metric_code,
		m.metric_value,
		m.metric_unit,
		l.device_type_code as device_type_id,
		l.measure_platform_code,
		l.measure_location
	from {{ ref('stg_discovery__lifelog_measurements') }} as m
	inner join {{ ref('stg_discovery__lifelog_user_info') }} as l using (user_lifelog_sn)
	inner join cohort as c on c.user_id = l.user_id

),

fact as (

	select
		user_id,
		source_stream,
		source_transaction_id,
		measured_at,
		metric_code,
		metric_value,
		metric_unit,
		device_type_id,
		measure_platform_code,
		measure_location
	from {{ ref('fct_measurement') }}

)

(select * from expected except all select * from fact)
union all
(select * from fact except all select * from expected)

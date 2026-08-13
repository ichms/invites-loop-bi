-- Grain: one row per distinct oxygen-saturation payload. Exact source
-- duplicates are collapsed, with their multiplicity retained.

with observations as (

	select
		user_lifelog_sn,
		measured_dt as measured_at,
		user_sleep_sn,
		oxygen_saturation,
		count(*)::bigint as source_row_count
	from {{ source('stg_discovery', 'disc_lifelog_user_oxygen_saturation') }}
	group by 1, 2, 3, 4

)

select
	{{ dbt_utils.generate_surrogate_key([
		'user_lifelog_sn',
		'measured_at',
		'user_sleep_sn',
		'oxygen_saturation',
	]) }} as source_observation_id,
	user_lifelog_sn,
	measured_at,
	user_sleep_sn,
	oxygen_saturation,
	source_row_count
from observations

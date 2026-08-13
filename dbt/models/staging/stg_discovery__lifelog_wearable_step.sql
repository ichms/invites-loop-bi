-- Grain: one row per distinct step payload. Exact source duplicates are
-- collapsed, with their multiplicity retained in source_row_count.

with observations as (

	select
		user_lifelog_sn,
		measured_dt as measured_at,
		step_cnt as step_count,
		kcal_burned,
		distance as distance_m,
		count(*)::bigint as source_row_count
	from {{ source('stg_discovery', 'disc_lifelog_user_step') }}
	group by 1, 2, 3, 4, 5

)

select
	{{ dbt_utils.generate_surrogate_key([
		'user_lifelog_sn',
		'measured_at',
		'step_count',
		'kcal_burned',
		'distance_m',
	]) }} as source_observation_id,
	user_lifelog_sn,
	measured_at,
	step_count,
	kcal_burned,
	distance_m,
	source_row_count
from observations

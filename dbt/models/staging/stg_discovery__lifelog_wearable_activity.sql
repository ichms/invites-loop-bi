-- Grain: one row per distinct activity interval payload. Exact source
-- duplicates are collapsed, with their multiplicity retained.

with observations as (

	select
		user_lifelog_sn,
		measured_dt as measured_at,
		measured_start_dt as started_at,
		measured_end_dt as ended_at,
		activity_type as activity_type_code,
		kcal_burned,
		distance as distance_m,
		count(*)::bigint as source_row_count
	from {{ source('stg_discovery', 'disc_lifelog_user_activity') }}
	group by 1, 2, 3, 4, 5, 6, 7

)

select
	{{ dbt_utils.generate_surrogate_key([
		'user_lifelog_sn',
		'measured_at',
		'started_at',
		'ended_at',
		'activity_type_code',
		'kcal_burned',
		'distance_m',
	]) }} as source_observation_id,
	user_lifelog_sn,
	measured_at,
	started_at,
	ended_at,
	activity_type_code,
	kcal_burned,
	distance_m,
	source_row_count
from observations

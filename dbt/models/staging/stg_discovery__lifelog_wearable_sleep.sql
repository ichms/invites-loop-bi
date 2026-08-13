-- Grain: one row per distinct sleep-session payload. user_sleep_sn is unique
-- today, but the full payload identity makes an in-place source correction
-- visible instead of silently choosing one version.

with observations as (

	select
		user_sleep_sn,
		user_lifelog_sn,
		total_measure_start_dt as started_at,
		total_measure_end_dt as ended_at,
		count(*)::bigint as source_row_count
	from {{ source('stg_discovery', 'disc_lifelog_user_sleep') }}
	group by 1, 2, 3, 4

)

select
	{{ dbt_utils.generate_surrogate_key([
		'user_sleep_sn',
		'user_lifelog_sn',
		'started_at',
		'ended_at',
	]) }} as source_observation_id,
	user_sleep_sn,
	user_lifelog_sn,
	started_at,
	ended_at,
	source_row_count
from observations

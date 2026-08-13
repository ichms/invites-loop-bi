-- Grain: one row per distinct sleep-stage interval payload. This source has
-- user_sleep_sn but no lifelog/user key; attribution happens through the sleep
-- session in fct_wearable_sleep_stage.

with observations as (

	select
		user_sleep_sn,
		sleep_stage as sleep_stage_code,
		measure_start_dt as started_at,
		measure_end_dt as ended_at,
		count(*)::bigint as source_row_count
	from {{ source('stg_discovery', 'disc_lifelog_user_sleep_detail') }}
	group by 1, 2, 3, 4

)

select
	{{ dbt_utils.generate_surrogate_key([
		'user_sleep_sn',
		'sleep_stage_code',
		'started_at',
		'ended_at',
	]) }} as source_observation_id,
	user_sleep_sn,
	sleep_stage_code,
	started_at,
	ended_at,
	source_row_count
from observations

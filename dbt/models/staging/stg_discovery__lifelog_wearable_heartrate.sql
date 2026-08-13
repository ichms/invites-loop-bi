-- Grain: one row per distinct heart-rate payload. A timestamp/type slot can
-- legitimately carry different values, so heartrate_count is part of the
-- observation identity. Only byte-for-byte-equivalent payloads collapse.

with observations as (

	select
		user_lifelog_sn,
		measured_dt as measured_at,
		heartrate_se_cd as heartrate_type_code,
		heartrate_cnt as heartrate_count,
		count(*)::bigint as source_row_count
	from {{ source('stg_discovery', 'disc_lifelog_user_heartrate') }}
	group by 1, 2, 3, 4

)

select
	{{ dbt_utils.generate_surrogate_key([
		'user_lifelog_sn',
		'measured_at',
		'heartrate_type_code',
		'heartrate_count',
	]) }} as source_observation_id,
	user_lifelog_sn,
	measured_at,
	heartrate_type_code,
	heartrate_count,
	source_row_count
from observations

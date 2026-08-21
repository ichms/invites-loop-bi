{{ config(
	materialized='incremental',
	incremental_strategy='window_replace',
	window_column='measured_at',
	window_lookback_days=30,
	on_schema_change='fail',
	indexes=[
		{'columns': ['source_observation_id'], 'unique': true},
		{'columns': ['measured_at']},
	]
) }}

-- GRAIN: one row per distinct heart-rate payload. A timestamp/type slot can
-- legitimately carry different values, so heartrate_count is part of the
-- observation identity. Only byte-for-byte-equivalent payloads collapse.
--
-- PHYSICAL PRIVATE INCREMENTAL. This is the one canonical expensive dedupe;
-- daily aggregation, detail attribution, and reconciliation must ref() it.
-- Incremental runs replace the latest 30-day event-time window. Use an
-- explicit --full-refresh after an older source correction or mapping-policy
-- change; never silently widen the routine window.

with observations as (

	select
		user_lifelog_sn,
		measured_dt as measured_at,
		heartrate_se_cd as heartrate_type_code,
		heartrate_cnt as heartrate_count,
		count(*)::bigint as source_row_count
	from {{ source('stg_discovery', 'disc_lifelog_user_heartrate') }}
	where measured_dt is not null
	{% if is_incremental() %}
		and measured_dt >= (
			select coalesce(
				max(measured_at) - interval '30 days',
				'-infinity'::timestamptz
			)
			from {{ this }}
		)
	{% endif %}
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

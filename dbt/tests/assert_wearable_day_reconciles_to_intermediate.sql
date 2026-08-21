{{ config(tags=['daily_core']) }}

-- P3 daily reconciliation. This deliberately compares the sparse daily fact
-- with the already-materialized daily intermediate; P4 separately proves the
-- source-grain detail and heart-rate incremental/full-refresh contracts.

with expected as (
	select
		w.user_id,
		w.wear_date as ymd_date,
		max(w.value_sum) filter (where w.stream_code = 'step') as step_count,
		max(w.kcal_sum) filter (where w.stream_code = 'step') as step_kcal,
		max(w.distance_sum) filter (where w.stream_code = 'step') as step_distance_m,
		max(w.duration_hours) filter (where w.stream_code = 'sleep') as sleep_hours,
		max(w.n_samples) filter (where w.stream_code = 'sleep') as sleep_sessions,
		max(w.kcal_sum) filter (where w.stream_code = 'activity') as activity_kcal,
		max(w.duration_hours) filter (where w.stream_code = 'activity') as activity_hours,
		max(w.n_samples) filter (where w.stream_code = 'activity') as activity_sessions,
		max(w.value_mean) filter (where w.stream_code = 'heartrate') as heartrate_mean,
		max(w.value_min) filter (where w.stream_code = 'heartrate') as heartrate_min,
		max(w.value_max) filter (where w.stream_code = 'heartrate') as heartrate_max,
		max(w.n_samples) filter (where w.stream_code = 'heartrate') as heartrate_samples,
		max(w.value_mean) filter (where w.stream_code = 'oxygen_saturation') as spo2_mean,
		max(w.value_min) filter (where w.stream_code = 'oxygen_saturation') as spo2_min,
		max(w.n_samples) filter (where w.stream_code = 'oxygen_saturation') as spo2_samples
	from {{ ref('stg_discovery__lifelog_wearable_day') }} as w
	inner join {{ ref('dim_user') }} as u using (user_id)
	group by 1, 2
),
actual as (
	select user_id, ymd_date, step_count, step_kcal, step_distance_m,
		sleep_hours, sleep_sessions, activity_kcal, activity_hours,
		activity_sessions, heartrate_mean, heartrate_min, heartrate_max,
		heartrate_samples, spo2_mean, spo2_min, spo2_samples
	from {{ ref('fct_wearable_day') }}
)
(select * from expected except all select * from actual)
union all
(select * from actual except all select * from expected)

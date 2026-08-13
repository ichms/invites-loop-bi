-- GRAIN: one row per (user_id, ymd_date) on which any wearable stream fired.
-- Enforced in marts.yml; never cut (D-04).
--
-- Daily intensity, not sample-level and not presence. Heartrate is ~785
-- samples per user-day and does not belong in fct_measurement (a fact of
-- discrete readings). Source-grain observations live in the six
-- fct_wearable_* facts. fct_user_day already has wearable_streams_active as
-- the wear-day flag; this fact is the daily values.
--
-- SPARSE. A missing row means no stream fired that day. A NULL column on a
-- present row means that stream did not fire — not that the user walked 0
-- steps or had a heart rate of 0. Do not coalesce these to 0 on the dense
-- fct_user_day spine.
--
-- Sleep is dated from total_measure_start_dt (same as the presence model),
-- so an overnight session that spans midnight sits on the start date.

with wearable as (

	select
		user_id,
		wear_date,
		stream_code,
		n_samples,
		value_sum,
		value_mean,
		value_min,
		value_max,
		kcal_sum,
		distance_sum,
		duration_hours
	from {{ ref('stg_discovery__lifelog_wearable_day') }}

),

users as (

	select user_id
	from {{ ref('dim_user') }}

)

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
from wearable as w
inner join users as u using (user_id)
group by 1, 2

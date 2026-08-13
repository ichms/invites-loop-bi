-- Grain: one row per (user_lifelog_sn, metric_code, measured_at) — the tall
-- form of every DISCRETE lifelog reading. Backs fct_measurement.
--
-- Tall, not one model per measurement type: the source tables are five
-- different shapes carrying the same idea (a number, a unit, a time, a device),
-- and a Superset user filtering `metric_code = 'systolic_bp'` is doing exactly
-- what a wide model would make them do with a column picker. One model also
-- means one grain test instead of five.
--
-- DELIBERATELY EXCLUDED, with reasons — this fact is for discrete readings:
--   heartrate     8.5M continuous samples over 17k transactions. This is the
--                 bimodal-density problem the decision log names; mixing a
--                 sampling stream into a fact of discrete readings makes every
--                 unqualified count meaningless. It has source-grain
--                 fct_wearable_heartrate plus the fct_wearable_day aggregate.
--   oxygen_sat    60k samples, same shape as heartrate.
--   sleep,
--   activity,
--   step          interval/period aggregates (start+end, or a daily total),
--                 not point-in-time readings — a different grain.
--   food, meal    nutrition, a different grain again (and meal images are not
--                 extracted at all).
--
-- DEDUPE: these tables have no primary key upstream. Exact duplicate rows exist
-- (re-deliveries) and `distinct` removes them. body_info additionally has 27
-- (transaction, timestamp) pairs carrying genuinely different values — a
-- correction with no ordering column to resolve it — so `distinct on` picks one
-- deterministically by value. assert_lifelog_body_info_ambiguity_bounded warns
-- if that count grows.

with body_info_deduped as (

	select distinct on (user_lifelog_sn, measured_dt)
		user_lifelog_sn,
		measured_dt,
		weight,
		height,
		bmi
	from (select distinct * from {{ source('stg_discovery', 'disc_lifelog_user_body_info') }}) as b
	order by
		user_lifelog_sn,
		measured_dt,
		weight desc nulls last,
		height desc nulls last,
		bmi desc nulls last

),

blood_pressure as (

	select distinct
		user_lifelog_sn,
		measured_dt as measured_at,
		unnest(array['systolic_bp', 'diastolic_bp', 'pulse']) as metric_code,
		unnest(array[systolic, diastolic, pulse])::numeric as metric_value,
		unnest(array['mmHg', 'mmHg', 'bpm']) as metric_unit
	from {{ source('stg_discovery', 'disc_lifelog_user_bloodpressure') }}

),

body_info as (

	select
		user_lifelog_sn,
		measured_dt as measured_at,
		unnest(array['weight', 'height', 'bmi']) as metric_code,
		unnest(array[weight, height, bmi])::numeric as metric_value,
		unnest(array['kg', 'cm', 'kg/m2']) as metric_unit
	from body_info_deduped

),

body_fat as (

	select distinct
		user_lifelog_sn,
		measured_dt as measured_at,
		unnest(array['skeletal_muscle_mass', 'body_fat_mass', 'body_fat_percentage']) as metric_code,
		unnest(array[skeletal_muscle_mass, body_fat_mass, body_fat_percentage])::numeric as metric_value,
		unnest(array['kg', 'kg', '%']) as metric_unit
	from {{ source('stg_discovery', 'disc_lifelog_user_bodyfat') }}

),

grip_strength as (

	select distinct
		user_lifelog_sn,
		measured_dt as measured_at,
		unnest(array['grip_strength_left', 'grip_strength_right']) as metric_code,
		unnest(array[left_hand_grip_strength, right_hand_grip_strength])::numeric as metric_value,
		unnest(array['kg', 'kg']) as metric_unit
	from {{ source('stg_discovery', 'disc_lifelog_user_grip_strength') }}

),

blood_glucose as (

	-- The source column carries TWO units with nothing marking which: 20
	-- readings at 5.3–6.9 (mmol/L) and 20 at 68–225 (mg/dL), measured
	-- 2026-08-06. Owner decision 2026-08-06: normalise everything to mg/dL,
	-- the unit used clinically in Korea and the US.
	--
	-- Detection threshold = 30, and the gap it sits in is wide: the highest
	-- mmol/L reading is 6.94 and the lowest mg/dL reading is 68. It is also
	-- defensible beyond this dataset — 30 mg/dL is profound hypoglycaemia
	-- (medical emergency, not something a home meter logs quietly), while
	-- 30 mmol/L is 540 mg/dL, extreme hyperglycaemia. Anything below 30 is
	-- therefore far more plausibly mmol/L than mg/dL.
	--
	-- The heuristic polices itself: assert_glucose_unit_gap_holds fails the
	-- build if a reading ever lands in the ambiguous 25–50 band, where the rule
	-- would be guessing rather than reading a clear gap. Zero such rows today.
	select distinct
		user_lifelog_sn,
		measured_dt as measured_at,
		'blood_glucose' as metric_code,
		case
			when glucose::numeric < 30 then round(glucose::numeric * 18.0182, 1)
			else glucose::numeric
		end as metric_value,
		'mg/dL' as metric_unit
	from {{ source('stg_discovery', 'disc_lifelog_user_bloodglucose') }}

),

unioned as (

	select * from blood_pressure
	union all select * from body_info
	union all select * from body_fat
	union all select * from grip_strength
	union all select * from blood_glucose

)

select
	user_lifelog_sn,
	measured_at,
	metric_code,
	metric_value,
	metric_unit
from unioned
-- A NULL reading is an absent measurement, not a measurement of nothing: the
-- source tables carry one row per device submission and leave unreported
-- metrics null (a scale that reports weight but not BMI).
where metric_value is not null

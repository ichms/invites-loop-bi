-- Grain: one row per (user_id, wear_date, stream_code) — the days on which a
-- wearable stream produced anything for a user, plus that day's aggregates.
--
-- PHYSICAL PRIVATE TABLE, unlike staging views. `heartrate` alone
-- is ~8.5M sample rows; as a view this would re-scan on every downstream query
-- and every Superset chart. It collapses to a few thousand user-days, so the
-- table is small even though its input is not.
--
-- STREAM UNION, not one stream: the historical measurement work settled the
-- definition of "has a device" as the union of step, activity, sleep, SpO2 and
-- heartrate, after three competing definitions produced 130, 157 and 167 and
-- the dashboard quoted them interchangeably. Keeping the stream as a column
-- means the union is the default and any single-stream definition stays
-- reconstructible, rather than being re-litigated per question.
--
-- C3's "167 users" IS NOT A CONSTANT — do not treat it as a target to match.
-- Reconciled 2026-08-10. At the same 2026-07-31 cutoff under the same union,
-- the panel read 177 before that day's backfill and 181 after it. Neither is a
-- defect: this data grows retroactively. Wearables sync late, so rows for a past
-- date keep arriving for ~4 weeks after it. Measured: 454 step rows for dates
-- <= 2026-08-06 landed at the source AFTER our 2026-08-06 full read, reaching
-- 29 days back. 167 was a true reading of a smaller snapshot; the count for any
-- fixed cutoff rises with extraction date and will keep rising.
-- ALWAYS QUOTE A WEARABLE COUNT WITH THE EXTRACTION DATE ATTACHED.
--
-- All five streams re-read a 30-day window (`lookback_days` in
-- discovery_targets.py). Heart rate joined on 2026-08-13 when fct_wearable_day
-- started using mean/min/max — presence did not need it (step is a strict
-- superset of wearers), intensity does.
--
-- STEP ALONE DETERMINES THE UNION. Measured 2026-08-10 after the backfill: every
-- user with any stream also has step — 186 of 186 unrestricted, zero users with
-- a stream but no step — so the five-way union is operationally "has step data".
-- 44 in-cohort users have step and nothing else, at well under half the
-- day-density of the rest (median 38 wear days vs 95). Phones count steps
-- without a watch and no column here distinguishes the two, so step-inclusive
-- counts device ownership only if you accept phone pedometers as devices. That
-- choice is the whole gap between 181 and 137 (union excluding step) and it
-- belongs to the owner, not to this model.
--
-- Presence vs intensity: fct_user_day still counts distinct stream_code
-- (wear-day). fct_wearable_day pivots the value_* / kcal / duration columns.
-- NULL in those columns means the stream has no such measure, not zero.
-- Date is derived on the KST boundary (D-18), matching `ymd` everywhere else.
-- Sleep is dated from total_measure_start_dt, same as presence; overnight
-- sessions that span midnight sit on the start date.

{{ config(
	materialized='incremental',
	incremental_strategy='window_replace',
	window_column='wear_date',
	window_lookback_days=30,
	on_schema_change='fail',
	indexes=[
		{'columns': ['user_id', 'wear_date', 'stream_code'], 'unique': true},
		{'columns': ['wear_date']},
	]
) }}

{% set streams = [
	{
		'table': 'disc_lifelog_user_step',
		'ts': 'measured_dt',
		'code': 'step',
		'value': 'step_cnt',
		'kcal': 'kcal_burned',
		'distance': 'distance',
		'duration': none,
	},
	{
		'table': 'disc_lifelog_user_activity',
		'ts': 'measured_dt',
		'code': 'activity',
		'value': none,
		'kcal': 'kcal_burned',
		'distance': 'distance',
		'duration': 'extract(epoch from (s.measured_end_dt - s.measured_start_dt)) / 3600.0',
	},
	{
		'table': 'disc_lifelog_user_oxygen_saturation',
		'ts': 'measured_dt',
		'code': 'oxygen_saturation',
		'value': 'oxygen_saturation',
		'kcal': none,
		'distance': none,
		'duration': none,
	},
	{
		'table': 'disc_lifelog_user_sleep',
		'ts': 'total_measure_start_dt',
		'code': 'sleep',
		'value': none,
		'kcal': none,
		'distance': none,
		'duration': 'extract(epoch from (s.total_measure_end_dt - s.total_measure_start_dt)) / 3600.0',
	},
] %}

with lifelog_user as (

	select user_lifelog_sn, user_id
	from {{ ref('stg_discovery__lifelog_user_info') }}

),

wear_days as (

{% for stream in streams %}
	select
		li.user_id,
		(s.{{ stream.ts }} at time zone 'Asia/Seoul')::date as wear_date,
		'{{ stream.code }}' as stream_code,
		count(*)::bigint as n_samples,
		{% if stream.value %}
		sum(s.{{ stream.value }})::numeric as value_sum,
		avg(s.{{ stream.value }})::numeric as value_mean,
		min(s.{{ stream.value }})::numeric as value_min,
		max(s.{{ stream.value }})::numeric as value_max,
		{% else %}
		null::numeric as value_sum,
		null::numeric as value_mean,
		null::numeric as value_min,
		null::numeric as value_max,
		{% endif %}
		{% if stream.kcal %}
		sum(s.{{ stream.kcal }})::numeric as kcal_sum,
		{% else %}
		null::numeric as kcal_sum,
		{% endif %}
		{% if stream.distance %}
		sum(s.{{ stream.distance }})::numeric as distance_sum,
		{% else %}
		null::numeric as distance_sum,
		{% endif %}
		{% if stream.duration %}
		sum({{ stream.duration }})::numeric as duration_hours
		{% else %}
		null::numeric as duration_hours
		{% endif %}
	from {{ source('stg_discovery', stream.table) }} as s
	inner join lifelog_user as li using (user_lifelog_sn)
	where s.{{ stream.ts }} is not null
	{% if is_incremental() %}
		and (s.{{ stream.ts }} at time zone 'Asia/Seoul')::date >= (
			select coalesce(max(wear_date) - 30, '-infinity'::date)
			from {{ this }}
		)
	{% endif %}
	group by 1, 2, 3
	union all
{% endfor %}
	select
		li.user_id,
		(h.measured_at at time zone 'Asia/Seoul')::date as wear_date,
		'heartrate' as stream_code,
		sum(h.source_row_count)::bigint as n_samples,
		sum(h.heartrate_count::numeric * h.source_row_count)::numeric as value_sum,
		(
			sum(h.heartrate_count::numeric * h.source_row_count)
			/ nullif(sum(h.source_row_count), 0)
		)::numeric as value_mean,
		min(h.heartrate_count)::numeric as value_min,
		max(h.heartrate_count)::numeric as value_max,
		null::numeric as kcal_sum,
		null::numeric as distance_sum,
		null::numeric as duration_hours
	from {{ ref('stg_discovery__lifelog_wearable_heartrate') }} as h
	inner join lifelog_user as li using (user_lifelog_sn)
	where h.measured_at is not null
	{% if is_incremental() %}
		and (h.measured_at at time zone 'Asia/Seoul')::date >= (
			select coalesce(max(wear_date) - 30, '-infinity'::date)
			from {{ this }}
		)
	{% endif %}
	group by 1, 2, 3

)

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
from wear_days

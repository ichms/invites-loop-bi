{{ config(materialized='table') }}

-- Grain: one row per (user_id, wear_date, stream_code) — the days on which a
-- wearable stream produced anything for a user.
--
-- MATERIALIZED AS A TABLE, unlike every other staging model. `heartrate` alone
-- is ~8.5M sample rows; as a view this would re-scan on every downstream query
-- and every Metabase card. It collapses to a few thousand user-days, so the
-- table is small even though its input is not.
--
-- STREAM UNION, not one stream: DASHBOARD_METRIC_FEEDBACK C3 settled the
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
-- The extractor now re-reads a 30-day window on four of the five streams
-- (`lookback_days` in discovery_targets.py), so the gap against source closes on
-- every run instead of accumulating. Heartrate is deliberately excluded there.
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
-- WEAR-DAY, NOT INTENSITY, is the point. §1.1④ found 91.6% of device holders at
-- a perfect 30/30 peak: a worn watch accumulates data passively, so density
-- measures willingness far less than it measures ownership. Counting days a
-- stream fired is the honest primitive; anything finer invites the reading that
-- §1.2 already disproved.
--
-- Date is derived on the KST boundary (D-18), matching `ymd` everywhere else.

{% set streams = [
	('disc_lifelog_user_step',              'measured_dt',             'step'),
	('disc_lifelog_user_activity',          'measured_dt',             'activity'),
	('disc_lifelog_user_heartrate',         'measured_dt',             'heartrate'),
	('disc_lifelog_user_oxygen_saturation', 'measured_dt',             'oxygen_saturation'),
	('disc_lifelog_user_sleep',             'total_measure_start_dt',  'sleep'),
] %}

with lifelog_user as (

	select user_lifelog_sn, user_id
	from {{ ref('stg_discovery__lifelog_user_info') }}

),

wear_days as (

{% for table_name, ts_column, stream_code in streams %}
	select distinct
		li.user_id,
		(s.{{ ts_column }} at time zone 'Asia/Seoul')::date as wear_date,
		'{{ stream_code }}' as stream_code
	from {{ source('stg_discovery', table_name) }} as s
	inner join lifelog_user as li using (user_lifelog_sn)
	where s.{{ ts_column }} is not null
{% if not loop.last %}
	union all
{% endif %}
{% endfor %}

)

select
	user_id,
	wear_date,
	stream_code
from wear_days

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
-- heartrate (167 users), after three competing definitions produced 130, 157
-- and 167 and the dashboard quoted them interchangeably. Keeping the stream as
-- a column means the union is the default and any single-stream definition
-- stays reconstructible, rather than being re-litigated per question.
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

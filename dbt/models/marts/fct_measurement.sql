-- GRAIN: one row per (user_id, source transaction, measured_at, metric_code).
-- Enforced in marts.yml; never cut (D-04).
--
-- Tall by metric_code: BP, body composition, grip strength and glucose all
-- arrive as "a number with a unit at a time from a device", so one fact with a
-- metric_code column beats five near-identical facts. device_type_id is a FK to
-- dim_device_type precisely so the density difference between a cuff and a
-- smartwatch is sliceable rather than a footnote (decision log's fct_measurement
-- note).
--
-- Continuous streams (heartrate, oxygen saturation) and interval aggregates
-- (sleep, activity, steps) are NOT here — see the staging model header for why
-- each is excluded and what it would need instead.
--
-- The user linkage runs through stg_discovery__lifelog_user_info: the
-- per-measurement tables carry no user key at all. That parent table only
-- became available on 2026-08-06 (it was not an extraction target); without it
-- this fact cannot exist.

with measurements as (

	select
		source_stream,
		user_lifelog_sn,
		measured_at,
		metric_code,
		metric_value,
		metric_unit
	from {{ ref('stg_discovery__lifelog_measurements') }}

),

lifelog as (

	select
		user_lifelog_sn,
		user_id,
		device_type_code,
		measure_platform_code,
		measure_location
	from {{ ref('stg_discovery__lifelog_user_info') }}

),

users as (

	select user_id
	from {{ ref('dim_user') }}

)

-- Do not collapse the apparent user/time/metric slot. On 2026-08-21 there were
-- 41 repeated slots and nine carried different platform codes. The source
-- transaction, device, platform, and location are therefore part of the
-- observation semantics, even when value and unit happen to agree.
select
	l.user_id,
	m.source_stream,
	m.user_lifelog_sn as source_transaction_id,
	m.measured_at,
	(m.measured_at at time zone 'Asia/Seoul')::date as measured_date,
	m.metric_code,
	m.metric_value,
	m.metric_unit,
	l.device_type_code as device_type_id,
	l.measure_platform_code,
	l.measure_location
from measurements as m
-- Inner join: a measurement with no parent transaction has no user and cannot
-- be attributed. assert_measurements_all_attributed pins that count at zero, so
-- a silent orphan becomes a build failure rather than a quiet undercount.
inner join lifelog as l using (user_lifelog_sn)
-- Cohort only, same guard as the other facts.
inner join users as u on u.user_id = l.user_id

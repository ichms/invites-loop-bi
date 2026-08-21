{{ config(tags=['p4_heartrate_audit']) }}

-- Expensive P4 audit, intentionally outside daily_core and wearable_detail.
-- Run it once after the measured full refresh and again after an incremental
-- window replacement. Passing in both states proves their equality through
-- the same full-source definition without making routine builds regroup raw
-- heart-rate rows.

with lifelog_user as (

	select user_lifelog_sn, user_id
	from {{ ref('stg_discovery__lifelog_user_info') }}

),

source_total as (

	select count(*)::bigint as source_rows
	from {{ source('stg_discovery', 'disc_lifelog_user_heartrate') }}
	where measured_dt is not null

),

dedupe_total as (

	select sum(source_row_count)::bigint as source_rows
	from {{ ref('stg_discovery__lifelog_wearable_heartrate') }}

),

raw_daily as (

	select
		li.user_id,
		(h.measured_dt at time zone 'Asia/Seoul')::date as wear_date,
		count(*)::bigint as n_samples,
		sum(h.heartrate_cnt)::numeric as value_sum,
		avg(h.heartrate_cnt)::numeric as value_mean,
		min(h.heartrate_cnt)::numeric as value_min,
		max(h.heartrate_cnt)::numeric as value_max
	from {{ source('stg_discovery', 'disc_lifelog_user_heartrate') }} as h
	inner join lifelog_user as li using (user_lifelog_sn)
	where h.measured_dt is not null
	group by 1, 2

),

dedupe_daily as (

	select
		li.user_id,
		(h.measured_at at time zone 'Asia/Seoul')::date as wear_date,
		sum(h.source_row_count)::bigint as n_samples,
		sum(h.heartrate_count::numeric * h.source_row_count)::numeric as value_sum,
		(
			sum(h.heartrate_count::numeric * h.source_row_count)
			/ nullif(sum(h.source_row_count), 0)
		)::numeric as value_mean,
		min(h.heartrate_count)::numeric as value_min,
		max(h.heartrate_count)::numeric as value_max
	from {{ ref('stg_discovery__lifelog_wearable_heartrate') }} as h
	inner join lifelog_user as li using (user_lifelog_sn)
	group by 1, 2

),

wearable_daily as (

	select
		user_id,
		wear_date,
		n_samples,
		value_sum,
		value_mean,
		value_min,
		value_max
	from {{ ref('stg_discovery__lifelog_wearable_day') }}
	where stream_code = 'heartrate'

),

source_count_mismatch as (

	select
		'source_row_count'::text as mismatch_scope,
		null::uuid as user_id,
		null::date as wear_date
	from source_total
	cross join dedupe_total
	where source_total.source_rows is distinct from dedupe_total.source_rows

),

daily_mismatch as (

	select
		'raw_dedupe_or_wearable_day'::text as mismatch_scope,
		coalesce(r.user_id, d.user_id, w.user_id) as user_id,
		coalesce(r.wear_date, d.wear_date, w.wear_date) as wear_date
	from raw_daily as r
	full outer join dedupe_daily as d using (user_id, wear_date)
	full outer join wearable_daily as w using (user_id, wear_date)
	where row(
		r.n_samples, r.value_sum, r.value_mean, r.value_min, r.value_max
	) is distinct from row(
		d.n_samples, d.value_sum, d.value_mean, d.value_min, d.value_max
	)
		or row(
		d.n_samples, d.value_sum, d.value_mean, d.value_min, d.value_max
	) is distinct from row(
		w.n_samples, w.value_sum, w.value_mean, w.value_min, w.value_max
	)

)

select * from source_count_mismatch
union all
select * from daily_mismatch

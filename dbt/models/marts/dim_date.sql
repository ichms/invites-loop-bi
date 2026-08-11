-- Grain: one row per calendar day.
--
-- Generated, not sourced. Spans 2025-01-01 (the year the cohort data starts)
-- through the end of next year, so "this year"/"next month" filters in Superset
-- always have rows to land on. Rebuilt on every dbt run, so the window rolls
-- forward on its own.
--
-- Week semantics match MB_START_OF_WEEK=monday (D-18): week_start_date is the
-- Monday of the week. Timezone is not a concern here — these are business
-- dates, matching the `ymd` grain the facts carry.

with spine as (

	select generate_series(
		date '2025-01-01',
		(date_trunc('year', current_date) + interval '2 years - 1 day')::date,
		interval '1 day'
	)::date as date_day

)

select
	date_day,
	extract(year from date_day)::int as year_number,
	extract(quarter from date_day)::int as quarter_number,
	extract(month from date_day)::int as month_number,
	to_char(date_day, 'YYYY-MM') as year_month,
	to_char(date_day, 'Month') as month_name,
	extract(day from date_day)::int as day_of_month,
	-- isodow: Monday = 1 .. Sunday = 7
	extract(isodow from date_day)::int as day_of_week,
	to_char(date_day, 'Day') as day_name,
	(date_trunc('week', date_day))::date as week_start_date,
	extract(week from date_day)::int as iso_week_number,
	extract(isodow from date_day) >= 6 as is_weekend
from spine

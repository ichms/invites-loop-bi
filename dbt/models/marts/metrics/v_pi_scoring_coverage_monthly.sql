-- PI: 점수 산출 커버리지 (월별) — what share of the enrolled cohort actually
-- received a risk score that month.
--
-- A data-quality PI, and the one that qualifies every other number here: if
-- coverage falls, "mean risk improved" may only mean the sickest users stopped
-- being scored. Read this view before citing v_pi_population_risk_monthly.

select
	d.month_start_date,
	(select count(*) from {{ ref('dim_user') }}) as cohort_size,
	d.users_scored,
	round(100.0 * d.users_scored / nullif((select count(*) from {{ ref('dim_user') }}), 0), 1) as coverage_pct
from (
	select
		date_trunc('month', ymd_date)::date as month_start_date,
		count(distinct user_id) as users_scored
	from {{ ref('fct_user_disease_day') }}
	group by 1
) as d

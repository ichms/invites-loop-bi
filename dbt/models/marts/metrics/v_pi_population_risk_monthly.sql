-- PI: 인구집단 위험도 추이 (월별) — mean IRS+ across the catalog diseases.
--
-- IRS+ is a 1–100 PERCENTILE RANK, so this is a population's average standing,
-- not an absolute risk level: it can only be read as movement over time, and
-- never summed or subtracted (IMPLEMENTATION_PLAN.md §3.6).
--
-- Restricted to the 35 catalog diseases, so the number matches what users see.

select
	date_trunc('month', ymd_date)::date as month_start_date,
	count(distinct user_id) as users_scored,
	round(avg(irsp_score), 2) as mean_irs_plus,
	round(avg(irs_score), 2) as mean_irs
from {{ ref('fct_user_disease_day') }}
where is_in_catalog
	and irsp_score is not null
group by 1

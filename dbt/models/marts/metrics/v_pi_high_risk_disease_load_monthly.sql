-- PI: 고위험 질환 부담 (월별) — average number of catalog diseases per user
-- sitting in the top risk quintile.
--
-- "High risk" = irs_score >= 80, which is not an arbitrary cut: the scores ARE
-- percentile ranks (1–100), so >= 80 means "top 20% of the reference population
-- for this disease".
--
-- This deliberately measures the COUNT per user, not the share of users with at
-- least one. The share was tried first and discarded: across 35 diseases nearly
-- every user has at least one in the top quintile, so it read 86–94% every
-- month and could not move. The count discriminates, and it is the honest
-- reading of a per-disease percentile model — risk here is a load, not a label.

with per_user_month as (

	select
		date_trunc('month', ymd_date)::date as month_start_date,
		user_id,
		-- DISTINCT disease, not row count: a user is scored on many days in a
		-- month, so count(*) counts disease-days and inflates the load far past
		-- the 35-disease catalog (it read a max of 272 before this fix).
		count(distinct disease_id) filter (where irs_score >= 80) as high_risk_diseases
	from {{ ref('fct_user_disease_day') }}
	where is_in_catalog
		and irs_score is not null
	group by 1, 2

)

select
	month_start_date,
	count(*) as users_scored,
	round(avg(high_risk_diseases), 2) as avg_high_risk_diseases,
	max(high_risk_diseases) as max_high_risk_diseases
from per_user_month
group by 1

-- GRAIN: one row per (user_id, ymd_date, disease_id). Enforced by
-- dbt_utils.unique_combination_of_columns in marts.yml — never cut.
--
-- Kept separate from fct_user_day deliberately (decision log's explicit
-- warning): collapsing this into the user-day grain loses the per-condition
-- slice, which is the whole point of a 44-disease scoring engine.
--
-- SOURCE, corrected by measurement: the plan expected this fact to come from
-- exploding the `risk_overview[]` JSONB payload. It does not — the payload's
-- per-disease `irs_rank` is simply the IRS+ score (it equals irsp_score on
-- 12,806 of 12,900 matched user-day-disease rows, 99.3%), while
-- stg_irs.user_irs_hist carries all five scores relationally, typed, at an
-- exactly-verified grain. Building from the payload would mean re-deriving one
-- column that already exists and losing the other four. The payload stays the
-- source for narrative content (symptoms, care factors) if a model ever needs
-- it.
--
-- All five scores are integer percentile RANKS (1..100), not additive parts —
-- see the note in fct_user_day about the retired "residual" column.
--
-- Rows exist for all 44 scored diseases; only the 35 in dim_disease are
-- user-facing. is_in_catalog carries that distinction so the fact stays
-- complete while every disease-sliced metric filters on it (or joins the dim).

with scores as (

	select
		user_id,
		score_date as ymd_date,
		disease_id,
		irs_score,
		irsp_score,
		lrs_score,
		mrs_score,
		prs_score
	from {{ ref('stg_irs__user_irs_hist') }}

),

users as (

	select
		user_id,
		birth_year
	from {{ ref('dim_user') }}

),

catalog as (

	select disease_id
	from {{ ref('dim_disease') }}

)

select
	s.user_id,
	s.ymd_date,
	s.disease_id,
	c.disease_id is not null as is_in_catalog,

	s.irs_score,
	s.irsp_score,
	s.lrs_score,
	s.mrs_score,
	s.prs_score,

	-- D-25: age materialised in the fact, not the dim. Same July 1 anchor as
	-- fct_user_day (D-24) — the two must never diverge.
	case
		when u.birth_year is not null
			then ((s.ymd_date - make_date(u.birth_year, 7, 1)) / 365.25)::numeric(5, 2)
	end as age_at_activity,
	case
		when u.birth_year is not null
			then (floor(((s.ymd_date - make_date(u.birth_year, 7, 1)) / 365.25) / 5) * 5)::int
	end as age_band_5y
from scores as s
inner join users as u using (user_id)
left join catalog as c using (disease_id)

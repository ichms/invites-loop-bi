-- GRAIN: one row per (user_id, ymd_date). Enforced by
-- dbt_utils.unique_combination_of_columns in marts.yml. This declaration is the
-- contract — if a change makes it false, the build fails rather than quietly
-- doubling every count downstream (D-04).
--
-- The user-day spine is the UNION of the two things that happen per user-day,
-- because neither covers the other: 4,548 user-days have IRS scores, 5,499 have
-- an integrated analysis, and only 4,300 have both (measured 2026-08-06). An
-- inner join would silently discard ~1,400 user-days. The has_* flags make the
-- asymmetry a visible column instead of a mystery in a chart.
--
-- Per-disease scores are NOT here — they are in fct_user_disease_day, at
-- (user × ymd × disease). Collapsing them into this grain would lose the
-- condition slice, which the decision log warns about explicitly.
--
-- NOTE on the log's "explicit residual term": measurement retires it. IRS,
-- IRS+, LRS, MRS and PRS are integer percentile RANKS (1..100), not additive
-- components — IRS is an ML combination of PRS, updated LRS and updated MRS
-- (IRS-03 spec), and IRS − (PRS+LRS+MRS+IRSp) averages −135 with a 42-point
-- spread. There is no residual to carry, so no residual column exists. Do not
-- reintroduce one without re-reading the spec.

with intg as (

	select
		user_id,
		ymd_date,
		signature_description,
		signature_disease_type_code,
		signature_disease_type_label,
		signature_lifestyle_type_code,
		signature_lifestyle_type_label,
		signature_potential_type_code,
		signature_potential_type_label,
		signature_segment_type_code,
		signature_segment_type_label
	from {{ ref('stg_sibc__user_intg_log') }}

),

scores as (

	select
		user_id,
		score_date as ymd_date,
		count(*) as diseases_scored,
		count(*) filter (where irs_score is not null) as diseases_with_irs_score
	from {{ ref('stg_irs__user_irs_hist') }}
	group by 1, 2

),

spine as (

	select user_id, ymd_date from intg
	union
	select user_id, ymd_date from scores

),

users as (

	select
		user_id,
		birth_year
	from {{ ref('dim_user') }}

)

select
	sp.user_id,
	sp.ymd_date,

	-- D-24: age imputed from a fixed July 1 mid-year anchor. The anchor is a
	-- convention (UN population estimates), not a preference — never vary it,
	-- or age bands shift by one across models. Max error ±6 months, which is
	-- fine for 5-year bands and must be disclosed for anything narrower.
	case
		when u.birth_year is not null
			then ((sp.ymd_date - make_date(u.birth_year, 7, 1)) / 365.25)::numeric(5, 2)
	end as age_at_activity,

	-- Q-12: the band is what Metabase surfaces; raw age above stays for
	-- view-layer computation. At n=404, raw age in a GUI filter makes
	-- small-cell exposure trivially reachable.
	case
		when u.birth_year is not null
			then (floor(((sp.ymd_date - make_date(u.birth_year, 7, 1)) / 365.25) / 5) * 5)::int
	end as age_band_5y,

	i.signature_description,
	i.signature_disease_type_code,
	i.signature_disease_type_label,
	i.signature_lifestyle_type_code,
	i.signature_lifestyle_type_label,
	i.signature_potential_type_code,
	i.signature_potential_type_label,
	i.signature_segment_type_code,
	i.signature_segment_type_label,

	coalesce(s.diseases_scored, 0) as diseases_scored,
	coalesce(s.diseases_with_irs_score, 0) as diseases_with_irs_score,

	i.user_id is not null as has_intg_analysis,
	s.user_id is not null as has_irs_scores
from spine as sp
left join intg as i using (user_id, ymd_date)
left join scores as s using (user_id, ymd_date)
-- Cohort only. Verified 2026-08-06: every scoring user is in user_master, so
-- this join drops nothing today; it is here so a future non-cohort user cannot
-- silently appear in the fact.
inner join users as u using (user_id)

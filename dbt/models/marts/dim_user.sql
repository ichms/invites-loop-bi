-- Grain: one row per user_id. SCD Type 1 (D-08) — attributes reflect the latest
-- state; anything time-varying belongs in a fact at event time.
--
-- Population = the current sibc cohort (`user_master`), per N-02 — NOT the
-- iccoli mapper. Mapper-only entries have no sibc presence and therefore no
-- facts; a staging test counts them dynamically rather than modelling them.
-- `is_mapped` keeps cohort members with no iccoli link in the dimension with
-- their sibc facts intact, instead of orphaning them behind a join.
--
-- Deliberately absent:
--   name / DOB          direct identifiers; never landed (PII_INVENTORY.md R-4)
--   age                 time-varying — a static age in an SCD1 dim rots within
--                       a year (D-25). Age lives in the facts, computed at
--                       activity time.
--   device allocation   an earlier design named a device-allocation flag, but
--                       NO source system carries one (checked across
--                       all five landing schemas 2026-08-06). Deferred rather
--                       than derived from measurement activity, which would be
--                       a metric definition wearing a dimension's clothes.
--   site                current site lives in bridge_user_site_current. The
--                       source has no history, so it must never be copied onto
--                       historical fact rows.
--
-- Legacy serving extensions present before the W-first redesign:
--   weight / height / bmi / bmi_band   enrolment/current-profile snapshot
--   cohort_group                      owner-maintained staff roster classification
-- Lifetime behaviour flags are deliberately absent. Eligibility and load
-- completeness are evaluated at each user-day in fct_user_day.

with cohort as (

	select
		user_id,
		sex,
		joined_dt,
		timezone,
		weight_kg,
		height_cm
	from {{ ref('stg_sibc__user_master') }}

),

mapped as (

	select user_id
	from {{ ref('stg_iccoli__tb_ext_user_mapper') }}

),

personal as (

	select
		user_id,
		birth_year
	from {{ ref('stg_iccoli__tb_user_personal_info') }}
	where user_id is not null

),

app_account as (

	select
		user_id,
		channel_type,
		status,
		create_datetime as app_registered_at
	from {{ ref('stg_iccoli__tb_user_info') }}
	where user_id is not null

),

staff as (

	-- Owner-maintained. See seeds/staff_roster.csv header in seeds.yml.
	select user_id::uuid as user_id
	from {{ ref('staff_roster') }}

)

select
	c.user_id,
	c.sex,
	-- Null birth years propagate into age_at_activity in the facts rather than
	-- being guessed at; coverage is tested dynamically.
	p.birth_year,
	c.joined_dt,
	c.timezone,
	m.user_id is not null as is_mapped,
	a.channel_type,
	a.status as app_account_status,
	a.app_registered_at,

	-- Enrolment anthropometrics. Asia-Pacific BMI bands (Korean public-health
	-- cutoffs): underweight <18.5, normal 18.5–<23, overweight 23–<25, obese ≥25.
	-- Historical analysis found BMI non-monotonic and age-confounded. Keep the
	-- band for controlled slicing, but never interpret it alone.
	c.weight_kg,
	c.height_cm,
	case
		when c.weight_kg is not null and c.height_cm is not null
			then round(
				(c.weight_kg::numeric / power(c.height_cm::numeric / 100, 2))::numeric,
				2
			)
	end as bmi,
	case
		when c.weight_kg is null or c.height_cm is null then null
		when (c.weight_kg::numeric / power(c.height_cm::numeric / 100, 2)) < 18.5
			then 'underweight'
		when (c.weight_kg::numeric / power(c.height_cm::numeric / 100, 2)) < 23
			then 'normal'
		when (c.weight_kg::numeric / power(c.height_cm::numeric / 100, 2)) < 25
			then 'overweight'
		else 'obese'
	end as bmi_band,

	-- Staff vs participant. Seed-backed so new hires with no behavioural
	-- history can be labelled. The contrast is "participation contract vs
	-- none", not an inferred behavioural distinction.
	case
		when s.user_id is not null then 'staff'
		else 'participant'
	end as cohort_group
from cohort as c
left join mapped as m using (user_id)
left join personal as p using (user_id)
left join app_account as a using (user_id)
left join staff as s using (user_id)

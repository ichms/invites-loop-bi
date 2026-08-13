-- Grain: one row per user_id. SCD Type 1 (D-08) — attributes reflect the latest
-- state; anything time-varying belongs in a fact at event time.
--
-- Population = the sibc cohort (`user_master`, 404 rows), per N-02 — NOT the
-- iccoli mapper. The 39 mapper-only entries have no sibc presence and therefore
-- no facts; they are counted by a staging test, not modelled here.
-- `is_mapped` keeps the cohort members who have no iccoli link (2 today) in the
-- dim with their sibc facts intact, instead of orphaning them behind a join.
--
-- Deliberately absent:
--   name / DOB          direct identifiers; never landed (PII_INVENTORY.md R-4)
--   age                 time-varying — a static age in an SCD1 dim rots within
--                       a year (D-25). Age lives in the facts, computed at
--                       activity time.
--   device allocation   the log's Q-06 attribute list names a device-allocation
--                       flag, but NO source system carries one (checked across
--                       all five landing schemas 2026-08-06). Deferred rather
--                       than derived from measurement activity, which would be
--                       a metric definition wearing a dimension's clothes.
--   site history        site_id is the current iCHMS site only. In-place source
--                       updates erase the prior value and actual switch time;
--                       historical/as-of attribution still needs a bridge.
--
-- Frame 2 extensions (todo.md item B, 2026-08-13):
--   weight / height / bmi / bmi_band   enrolment snapshot for segment moderation
--   cohort_group                      staff vs participant from staff_roster seed
--   is_observable_*                   per-channel ever-observed flags

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

),

current_site as (

	select user_id, site_id
	from {{ ref('stg_ichms__current_user_deployment_site') }}

),

observable_login as (

	select distinct user_id
	from {{ ref('stg_iccoli__tb_user_login_log') }}
	where user_id is not null

),

observable_routine as (

	-- Lifetime completion rate. §2.4's "둘 다 충족" used 수행률 ≥ 50%, so the
	-- intersection flag below needs the rate, not merely "ever delivered".
	select
		user_id,
		count(*) as routines_delivered,
		count(*) filter (where completed_at is not null) as routines_completed
	from {{ ref('stg_sibc__daily_routine_activities') }}
	group by 1

),

observable_manual as (

	-- Measurements key on user_lifelog_sn only; user_id comes from lifelog_user_info
	-- (same join fct_user_day / fct_measurement use).
	select distinct li.user_id
	from {{ ref('stg_discovery__lifelog_measurements') }} as ms
	inner join {{ ref('stg_discovery__lifelog_user_info') }} as li
		using (user_lifelog_sn)
	where li.user_id is not null

),

observable_meal as (

	select distinct user_id
	from {{ ref('stg_discovery__lifelog_meal') }}
	where user_id is not null

),

observable_wearable as (

	select distinct user_id
	from {{ ref('stg_discovery__lifelog_wearable_day') }}
	where user_id is not null

)

select
	c.user_id,
	-- Current-state SCD1 attribution, owner-approved 2026-08-13. This reflects
	-- the one active Ulsan/Jeju link now stored by iCHMS. It is suitable for a
	-- current-site filter, not historical/as-of analysis: the 13 known in-place
	-- Ulsan→Jeju updates carry neither their prior value nor switch timestamp.
	cs.site_id,
	c.sex,
	-- 400 of 404 cohort users have a birth year (the 4 without are the 2
	-- unmapped users plus 2 with no `birth` value upstream). Null propagates
	-- into age_at_activity in the facts rather than being guessed at.
	p.birth_year,
	c.joined_dt,
	c.timezone,
	m.user_id is not null as is_mapped,
	a.channel_type,
	a.status as app_account_status,
	a.app_registered_at,

	-- Enrolment anthropometrics. Asia-Pacific BMI bands (Korean public-health
	-- cutoffs): underweight <18.5, normal 18.5–<23, overweight 23–<25, obese ≥25.
	-- §2.5 found BMI non-monotonic and age-confounded — band for GUI filters,
	-- never interpret alone. Raw bmi stays for notebook covariate control.
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
	-- none", not "voluntary vs involuntary" (§1.5) — 29 of the broader staff
	-- pool historically had accounts only.
	case
		when s.user_id is not null then 'staff'
		else 'participant'
	end as cohort_group,

	-- Per-channel observability (Frame 2). Ever-observed, not current-state:
	-- these answer "who can even be measured on this channel", which is what
	-- makes the §2.4 exposure-vs-physiology population split computable.
	ol.user_id is not null as is_observable_app_login,
	orut.user_id is not null as is_observable_routine,
	om.user_id is not null as is_observable_manual_measurement,
	omeal.user_id is not null as is_observable_meal,
	ow.user_id is not null as is_observable_wearable,
	-- §2.4 intersection: wearable ownership AND lifetime routine completion
	-- rate ≥ 50%. That was 98 users in the July-31 analysis; recompute, do not
	-- hardcode.
	(
		ow.user_id is not null
		and coalesce(orut.routines_delivered, 0) > 0
		and (orut.routines_completed::numeric / orut.routines_delivered) >= 0.5
	) as is_observable_wearable_and_routine
from cohort as c
left join mapped as m using (user_id)
left join personal as p using (user_id)
left join app_account as a using (user_id)
left join staff as s using (user_id)
left join current_site as cs using (user_id)
left join observable_login as ol using (user_id)
left join observable_routine as orut using (user_id)
left join observable_manual as om using (user_id)
left join observable_meal as omeal using (user_id)
left join observable_wearable as ow using (user_id)

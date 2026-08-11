-- GRAIN: one row per (user_id, ymd_date). Enforced by
-- dbt_utils.unique_combination_of_columns in marts.yml. This declaration is the
-- contract — if a change makes it false, the build fails rather than quietly
-- doubling every count downstream (D-04).
--
-- ============================================================================
-- SPINE CHANGED 2026-08-07: SPARSE -> DENSE. Read this before touching it.
-- ============================================================================
-- This fact used to be the UNION of user-days that had an IRS score or an
-- integrated analysis: 5,747 rows, which is 9.3% of the 62,030 user-days the
-- cohort has actually lived. That was correct for a scoring-state fact and is
-- fatal for a behavioural one.
--
-- A behavioural panel needs the days a user did NOTHING, because those days are
-- the denominator. Aggregating activity over a spine that only contains active
-- days divides by the wrong number and biases every rate upward — which is not
-- hypothetical here: DASHBOARD_METRIC_FEEDBACK §5.2 records a published
-- "dietary logging is 미흡" verdict that was purely an artifact of a
-- whole-cohort denominator, reversed once the denominator was stated
-- (per-recorder intensity had risen 6.2 -> 21.1 days/month, not fallen).
--
-- The spine is therefore every day from the user's joined_dt to the observation
-- frontier. The has_* flags carry what the old spine carried implicitly: a row
-- with has_irs_scores = false is a day the user existed and was not scored,
-- which previously was an absent row and therefore invisible.
--
-- FRONTIER, not current_date: the upper bound is the latest day any behavioural
-- source has actually delivered. Extending to today would manufacture
-- zero-activity days for dates the ELT has not loaded yet, and a flat line of
-- false zeros at the right edge of every chart reads as a product collapse.
-- Per-channel lag is NOT modelled — if one source is stale its recent days show
-- as zeros while others show real activity. Check `dbt source freshness` before
-- reading the last few days of any channel.
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

with users as (

	select
		user_id,
		birth_year,
		joined_dt::date as joined_date
	from {{ ref('dim_user') }}

),

-- Behavioural sources, each collapsed to (user_id, ymd_date) before they meet
-- the spine. Aggregating first keeps the spine join one-to-one, so a source
-- that gains rows can never fan out the grain.

logins as (

	select
		user_id,
		(login_datetime at time zone 'Asia/Seoul')::date as ymd_date,
		count(*) as app_login_events
	from {{ ref('stg_iccoli__tb_user_login_log') }}
	group by 1, 2

),

routines as (

	-- The denominator pair. `delivered` is what the engine offered, `completed`
	-- is what the user did; a completion rate computed without both in the same
	-- row is the §5.2 error waiting to recur.
	select
		user_id,
		ymd_date,
		count(*) as routines_delivered,
		count(*) filter (where completed_at is not null) as routines_completed
	from {{ ref('stg_sibc__daily_routine_activities') }}
	group by 1, 2

),

measurements as (

	-- Measurements key on user_lifelog_sn and carry no user of their own; the
	-- join through lifelog_user_info is the only place they gain one.
	select
		li.user_id,
		(ms.measured_at at time zone 'Asia/Seoul')::date as ymd_date,
		count(*) as manual_measurements
	from {{ ref('stg_discovery__lifelog_measurements') }} as ms
	inner join {{ ref('stg_discovery__lifelog_user_info') }} as li
		using (user_lifelog_sn)
	group by 1, 2

),

meals as (

	select
		user_id,
		recorded_date as ymd_date,
		count(*) as meal_records
	from {{ ref('stg_discovery__lifelog_meal') }}
	group by 1, 2

),

wearable as (

	select
		user_id,
		wear_date as ymd_date,
		count(distinct stream_code) as wearable_streams_active
	from {{ ref('stg_discovery__lifelog_wearable_day') }}
	group by 1, 2

),

app_actions as (

	select
		user_id,
		(action_datetime at time zone 'Asia/Seoul')::date as ymd_date,
		count(*) as app_actions
	from {{ ref('stg_iccoli__tb_action_user_log') }}
	group by 1, 2

),

-- The observation frontier: the last day any behavioural source delivered.
-- See the FRONTIER note in the header for why this is not current_date.
frontier as (

	select max(ymd_date) as observed_through
	from (
		select max(ymd_date) as ymd_date from logins
		union all select max(ymd_date) from routines
		union all select max(ymd_date) from measurements
		union all select max(ymd_date) from meals
		union all select max(ymd_date) from wearable
		union all select max(ymd_date) from app_actions
	) as per_source

),

-- The user's first observed activity, which is NOT always on or after their
-- joined_dt. `joined_dt` is entry to the sibc study cohort; app usage predates
-- it for some users. Anchoring the spine on joined_dt alone silently dropped
-- 381 meal records and made 23 meal recorders vanish entirely (335 -> 312),
-- because their only records sat before enrolment. Measured 2026-08-07.
--
-- Keeping the pre-enrolment window is not merely defensive. §1.3 depends on
-- having a pre-period: the ownership-transfer natural experiment is only
-- identifiable because wear rates were observed before the incentive changed.
-- days_since_joined is negative there, deliberately.
activity_bounds as (

	select user_id, min(ymd_date) as first_activity_date
	from (
		select user_id, ymd_date from logins
		union all select user_id, ymd_date from routines
		union all select user_id, ymd_date from measurements
		union all select user_id, ymd_date from meals
		union all select user_id, ymd_date from wearable
		union all select user_id, ymd_date from app_actions
	) as all_activity
	group by 1

),

spine as (

	select
		u.user_id,
		d.date_day as ymd_date
	from users as u
	cross join frontier as f
	left join activity_bounds as ab using (user_id)
	inner join {{ ref('dim_date') }} as d
		on d.date_day between least(u.joined_date, coalesce(ab.first_activity_date, u.joined_date))
			and f.observed_through

),

intg as (

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

	-- Q-12: the band is what Superset surfaces; raw age above stays for
	-- view-layer computation. At n=404, raw age in a GUI filter makes
	-- small-cell exposure trivially reachable.
	case
		when u.birth_year is not null
			then (floor(((sp.ymd_date - make_date(u.birth_year, 7, 1)) / 365.25) / 5) * 5)::int
	end as age_band_5y,

	-- RELATIVE TIME. DASHBOARD_METRIC_FEEDBACK §2.1: calendar month mixes the
	-- cohort-entry effect with the behaviour change, because users enrolled
	-- across nine months. Trajectories are only comparable on time-since-join,
	-- which is how the same document found age bands moving in OPPOSITE
	-- directions (70+ at +28.7, 50s at −19.4) under a cohort average of +12.6
	-- that concealed both.
	--
	-- Censoring is NOT flagged per row — it is a property of an aggregate, not
	-- of a day. Later relative months contain only early registrants, so check
	-- the cell count before reading a trend at high month_since_joined.
	(sp.ymd_date - u.joined_date)::int as days_since_joined,
	(
		extract(year from age(sp.ymd_date, u.joined_date)) * 12
		+ extract(month from age(sp.ymd_date, u.joined_date))
	)::int as months_since_joined,

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

	-- BEHAVIOUR. Zero means the user was enrolled and did not do it; that is a
	-- measurement, not a missing value, which is the entire reason the spine is
	-- dense. Coalesce is load-bearing.
	--
	-- app_login_days is the dominant explanatory variable, not one channel among
	-- several: §4.5 found routine completion of ~24% at 0–5 login days against
	-- ~65–72% at 16+, and showed that controlling for it REVERSES the sign of
	-- the premium-content effect (−10.6pp to +7.0pp). §4.9 lists promoting it to
	-- a primary indicator as immediately actionable. Any behavioural comparison
	-- that does not condition on it is measuring app usage.
	coalesce(l.app_login_events, 0) as app_login_events,
	(l.user_id is not null) as did_login,

	coalesce(r.routines_delivered, 0) as routines_delivered,
	coalesce(r.routines_completed, 0) as routines_completed,

	coalesce(m.manual_measurements, 0) as manual_measurements,
	coalesce(ml.meal_records, 0) as meal_records,
	coalesce(w.wearable_streams_active, 0) as wearable_streams_active,
	coalesce(a.app_actions, 0) as app_actions,

	-- ACTIVE vs PASSIVE (§2.3). Manual measurement and meal logging require a
	-- deliberate act; a worn watch accumulates data on its own (§1.1④: 91.6% of
	-- holders at a perfect 30/30). Summing them into one "engagement" number
	-- averages a behaviour with a device state and is how the platform looked
	-- uniformly healthy while every active channel but meals was cooling.
	(coalesce(m.manual_measurements, 0) + coalesce(ml.meal_records, 0)) as active_input_events,
	(w.user_id is not null) as had_passive_collection,

	i.user_id is not null as has_intg_analysis,
	s.user_id is not null as has_irs_scores
from spine as sp
inner join users as u using (user_id)
left join intg as i using (user_id, ymd_date)
left join scores as s using (user_id, ymd_date)
left join logins as l using (user_id, ymd_date)
left join routines as r using (user_id, ymd_date)
left join measurements as m using (user_id, ymd_date)
left join meals as ml using (user_id, ymd_date)
left join wearable as w using (user_id, ymd_date)
left join app_actions as a using (user_id, ymd_date)

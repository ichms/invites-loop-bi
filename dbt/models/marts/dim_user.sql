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

with cohort as (

	select
		user_id,
		sex,
		joined_dt,
		timezone
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

)

select
	c.user_id,
	-- A HARDCODED LITERAL, and known to be the wrong shape (corrected
	-- 2026-08-10). This used to read "single site until a source system carries
	-- one" — but ichms.auth_user_customer already carries per-user site links,
	-- already landed in stg_ichms, and all 404 users here resolve to ULSAN
	-- through it. It is not read because affiliation is many-to-many: the owner
	-- needs "was in Ulsan and is now ALSO in Jeju", which a scalar cannot hold
	-- and which SCD Type 1 (D-08) would resolve by overwriting — silently
	-- re-attributing every historical fact for that user.
	--
	-- Replacing this with a real value is NOT the fix; it would encode the same
	-- one-value assumption with better provenance. The fix is a bridge at
	-- (user_id, site_id, valid_from, valid_to), leaving this dim at one row per
	-- user. See CLAUDE.md § "Site affiliation is multi-valued" and todo.md B0.
	'KR_LOOP_PILOT' as site_id,
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
	a.app_registered_at
from cohort as c
left join mapped as m using (user_id)
left join personal as p using (user_id)
left join app_account as a using (user_id)

-- Q-10 join hygiene: cohort users with no iccoli mapping are a REPORTED set,
-- never a silent absence. Known today (2026-08-06) — both real members, both
-- joined 2026-05-01, owner follow-up open on why they have no iccoli link:
--
--   2725eece-14f6-4cd1-9e61-6abf9ad92553   (found Phase 0)
--   fbe82bc5-85ef-4640-90c1-de87b6f16151   (found Phase 1 — the plan said 1;
--                                           measurement now says 2)
--   cf0e0d5f-90bf-4113-9468-594e83f77e3a   (found 2026-08-13 resume; joined
--                                           2026-05-01, same pattern as the pair)
--
-- The test fails when the set changes in EITHER direction:
--   - a new row with issue = 'new unmapped cohort user': find out who they are
--     before adding them to `known` — dim_user keeps them via is_mapped, but
--     their app-action facts are missing;
--   - a row with issue = 'known orphan resolved': they gained a mapping —
--     remove their uuid here and consider an iccoli watermark reset so their
--     pre-enrolment rows backfill (see iccoli_targets.py).

with unmapped as (

	select m.user_id
	from {{ ref('stg_sibc__user_master') }} as m
	left join {{ ref('stg_iccoli__tb_ext_user_mapper') }} as x using (user_id)
	where x.user_id is null

),

known (user_id) as (

	values
		('2725eece-14f6-4cd1-9e61-6abf9ad92553'::uuid),
		('fbe82bc5-85ef-4640-90c1-de87b6f16151'::uuid),
		('cf0e0d5f-90bf-4113-9468-594e83f77e3a'::uuid)

)

select
	coalesce(u.user_id, k.user_id) as user_id,
	case
		when k.user_id is null then 'new unmapped cohort user'
		else 'known orphan resolved - update this test'
	end as issue
from unmapped as u
full outer join known as k using (user_id)
where u.user_id is null or k.user_id is null

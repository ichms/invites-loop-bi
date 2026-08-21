-- Grain: one row per surviving meal record. The source has no primary key, so
-- the grain is asserted by row identity, not by a key test.
--
-- WHY THIS MODEL EXISTS AT ALL: an earlier dashboard substituted
-- `disc_lifelog_user_food` and reached a false conclusion about meal logging.
-- The canonical channel is `disc_lifelog_user_meal`; see the dense-panel
-- finding in IMPLEMENTATION_PLAN.md §2.7.
--
-- `meal_data` is deliberately NOT selected. It holds the meal payload
-- (including image references), and the table is heavy. Reading it is a policy
-- conversation governed by PII_INVENTORY.md, not a config edit.
--
-- Deleted rows are dropped here rather than passed through with a flag. A
-- soft-deleted meal is not a recording event, and leaving the decision to each
-- consumer invites inconsistent denominators.

select
	m.user_lifelog_sn,
	li.user_id,
	m.ins_dt as recorded_at,
	(m.ins_dt at time zone 'Asia/Seoul')::date as recorded_date
from {{ source('stg_discovery', 'disc_lifelog_user_meal') }} as m
-- The only place a lifelog row gains a user_id (see stg_discovery__lifelog_user_info).
inner join {{ ref('stg_discovery__lifelog_user_info') }} as li
	using (user_lifelog_sn)
where m.is_deleted is not true

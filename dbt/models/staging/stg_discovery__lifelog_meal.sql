-- Grain: one row per surviving meal record. The source has no primary key, so
-- the grain is asserted by row identity, not by a key test.
--
-- WHY THIS MODEL EXISTS AT ALL: the evidence dashboard reported the meal
-- channel as `disc_lifelog_user_food` — 11 users — and concluded dietary
-- logging was "미흡". That was the wrong table. The real channel is
-- `disc_lifelog_user_meal`: 335 users and ~36.5k records, the most durable
-- ACTIVE-input channel on the platform (median 15 recording days vs 4 for
-- manual measurement). See DASHBOARD_METRIC_FEEDBACK §5 and change C22.
--
-- `meal_data` is deliberately NOT selected. It holds the meal payload
-- (including image references), the table is heavy, and the analysis that
-- established the §5 result explicitly ran without it. Reading it is a policy
-- conversation (PII_INVENTORY), not a config edit.
--
-- Deleted rows are dropped here rather than passed through with a flag. A
-- soft-deleted meal is not a recording event, and leaving the decision to each
-- consumer is how the 11-vs-335 error happens twice. Raw count is 37,728;
-- surviving is ~36.5k, which is the number §5 reports.

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

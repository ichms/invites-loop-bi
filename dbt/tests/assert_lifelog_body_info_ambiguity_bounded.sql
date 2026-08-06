{{ config(severity='warn') }}

-- disc_lifelog_user_body_info has no primary key and no ordering column, and 27
-- (transaction, timestamp) pairs carry genuinely different weight/height/bmi
-- values (measured 2026-08-06) — a correction with nothing to resolve it by.
-- Staging picks one deterministically by value, which is defensible for 27 rows
-- out of ~3,000 and indefensible if it becomes 300: at that point the source
-- needs an ordering column, not a tie-break rule.

with deduped as (

	select distinct * from {{ source('stg_discovery', 'disc_lifelog_user_body_info') }}

)

select
	count(*) - count(distinct (user_lifelog_sn, measured_dt)) as ambiguous_pairs,
	27 as known_baseline
from deduped
having count(*) - count(distinct (user_lifelog_sn, measured_dt)) > 27

-- DATE milestones must not manufacture midnight timestamps; TIMESTAMP
-- milestones must carry the real source occurrence time.

select user_id, milestone_code, occurred_date, occurred_at, temporal_precision
from {{ ref('fct_user_milestone') }}
where (temporal_precision = 'DATE' and occurred_at is not null)
	or (temporal_precision = 'TIMESTAMP' and occurred_at is null)

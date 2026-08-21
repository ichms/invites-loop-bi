-- The measured source snapshot has no sender mismatch between a share link and
-- its interaction rows. This test does not upgrade the interaction to sender
-- activity; it only detects a change in the current source relationship.

select
	i.share_log_no,
	i.share_no,
	i.user_id as interaction_actor_user_id,
	l.user_id as link_actor_user_id
from {{ ref('fct_share_interaction_event') }} as i
inner join {{ ref('fct_share_link') }} as l using (share_no)
where i.user_id is distinct from l.user_id

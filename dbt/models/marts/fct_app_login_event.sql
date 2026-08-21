-- GRAIN: one app login event identified by user, timestamp, and channel.
-- The source is keyless; the measured 2026-08-21 landing has no duplicates at
-- this natural grain. The hash is a deterministic warehouse key, not a source
-- identifier.

select
	md5(concat_ws('|', l.user_id::text, l.login_datetime::text, coalesce(l.channel_type, ''))) as login_event_id,
	l.user_id,
	l.login_datetime as logged_in_at,
	(l.login_datetime at time zone 'Asia/Seoul')::date as login_date,
	l.channel_type
from {{ ref('stg_iccoli__tb_user_login_log') }} as l
inner join {{ ref('dim_user') }} as u using (user_id)

{{ config(severity='warn') }}

-- N-02: mapper entries with no sibc.user_master row have no facts anywhere —
-- they are counted, not modelled. 39 on 2026-08-06. Growth after an enrolment
-- wave is expected (update the pin); movement without one deserves a look.
-- Warn-severity: this number moves for legitimate reasons, unlike the unmapped
-- cohort set next door.

select
	count(*) as mapper_only_users,
	39 as expected
from {{ ref('stg_iccoli__tb_ext_user_mapper') }} as x
left join {{ ref('stg_sibc__user_master') }} as m using (user_id)
where m.user_id is null
having count(*) <> 39

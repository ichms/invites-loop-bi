{{ config(severity='warn') }}

-- stg_sibc__user_intg_log silently drops rows whose payload is an LLM
-- serialisation failure ({"error": "..."}). That is correct — they carry no
-- structured fields — but the drop must not become a leak: every error row is
-- a user-day potentially missing from the marts. 1 known row on 2026-08-06
-- (2026-03-29). A growing count means upstream generation is failing.

select
	count(*) as error_rows,
	1 as known_baseline
from {{ source('stg_sibc', 'user_intg_log') }}
where intg_anlys ? 'error'
having count(*) > 1

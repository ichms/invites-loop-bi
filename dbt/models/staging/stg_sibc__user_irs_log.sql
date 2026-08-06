-- Grain: one row per (user_id, ymd_date) — same Q-01 dedupe rule as
-- stg_sibc__user_intg_log (the two logs are paired writes; identical row and
-- group counts, measured 2026-08-06).
--
-- The source's irs_data column is deliberately never selected: it is a legacy
-- mixed-shape payload (array in recent rows; object in 467 frozen rows from
-- 2025-12/2026-03 — their USERNAME key was stripped in place 2026-08-06, see
-- PII_INVENTORY.md). irs_anlys carries exactly one allow-listed key,
-- risk_overview (per-disease irs_rank; the scalar scores live in
-- stg_irs__user_irs_hist).

with source as (

	select
		user_id,
		ymd,
		irs_anlys,
		created_at,
		updated_at
	from {{ source('stg_sibc', 'user_irs_log') }}

),

deduped as (

	select
		*,
		row_number() over (
			partition by user_id, ymd
			order by created_at desc
		) as rn
	from source

),

renamed as (

	select
		user_id,
		to_date(ymd, 'YYYYMMDD') as ymd_date,
		irs_anlys -> 'risk_overview' as risk_overview,
		created_at,
		updated_at
	from deduped
	where rn = 1

)

select * from renamed

-- Grain: one row per (user_id, ymd_date) — enforced by a unique test AFTER the
-- Q-01 dedupe (measured 2026-08-06: up to 22 intra-day recomputations per
-- group, created_at distinct in every group, payloads genuinely differ →
-- deterministic last-row-wins).
--
-- D-26: only allow-listed keys (seeds/jsonb_allowlist.csv, extract=true) leave
-- the payload. intg_anlys carries a top-level user_name key — it stays behind
-- by omission, as does the current_status narrative block. The scalar
-- IRS+/LRS/MRS/PRS scores do NOT live in this payload; they are relational in
-- stg_irs__user_irs_hist.

with source as (

	select
		user_id,
		ymd,
		intg_anlys,
		created_at,
		updated_at
	from {{ source('stg_sibc', 'user_intg_log') }}
	-- LLM serialisation failures land as {"error": "..."} with no structured
	-- fields. Dropped here so a same-day successful recomputation wins the
	-- dedupe; assert_intg_error_rows_bounded keeps the count from growing
	-- silently.
	where not (intg_anlys ? 'error')

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
		-- ymd is 'YYYYMMDD' varchar in the source; a malformed value makes
		-- to_date raise, which fails the build loudly — by design.
		to_date(ymd, 'YYYYMMDD') as ymd_date,

		intg_anlys -> 'risk_overview' as risk_overview,

		intg_anlys -> 'user_signature_type' ->> 'description' as signature_description,
		intg_anlys -> 'user_signature_type' -> 'diseaseType' ->> 'code' as signature_disease_type_code,
		intg_anlys -> 'user_signature_type' -> 'diseaseType' ->> 'label' as signature_disease_type_label,
		intg_anlys -> 'user_signature_type' -> 'lifestyleType' ->> 'code' as signature_lifestyle_type_code,
		intg_anlys -> 'user_signature_type' -> 'lifestyleType' ->> 'label' as signature_lifestyle_type_label,
		intg_anlys -> 'user_signature_type' -> 'potentialType' ->> 'code' as signature_potential_type_code,
		intg_anlys -> 'user_signature_type' -> 'potentialType' ->> 'label' as signature_potential_type_label,
		-- segmentType is absent on ~5% of rows (measured 2026-08-06: 348/6457).
		intg_anlys -> 'user_signature_type' -> 'segmentType' ->> 'code' as signature_segment_type_code,
		intg_anlys -> 'user_signature_type' -> 'segmentType' ->> 'label' as signature_segment_type_label,

		created_at,
		updated_at
	from deduped
	where rn = 1

)

select * from renamed

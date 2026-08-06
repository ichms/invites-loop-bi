-- Grain: one row per (user_id, score_date, disease_id) — verified exact in the
-- source on 2026-08-06 (180,969 rows, 44 disease ids) and enforced with a
-- unique test.
--
-- This table is where the scalar IRS+/LRS/MRS/PRS scores actually live. The
-- plan's Phase 1 note expected them inside the sibc JSONB payloads; measurement
-- says otherwise — the payloads only carry per-disease irs_rank. fct_user_day /
-- fct_user_disease_day build from here.
--
-- Score columns are null on ~19–23% of rows (a score is not computed for every
-- disease/day); the null-rate thresholds in staging.yml encode that baseline so
-- a key/column rename upstream (100% null) still fails loudly.

select
	user_id,
	-- create_date is 'YYYYMMDD' varchar; to_date raises on garbage — loud by design.
	to_date(create_date, 'YYYYMMDD') as score_date,
	disease_id,
	irs_score,
	irsp_score,
	lrs_score,
	mrs_score,
	prs_score,
	created_at
from {{ source('stg_irs', 'user_irs_hist') }}

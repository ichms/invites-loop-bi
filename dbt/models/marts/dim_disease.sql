-- Grain: one row per disease_id. The 35 user-facing diseases, from the product
-- catalogue (`docs/01_product_specs/IRS-disease-catalog.csv`, seeded as
-- irs_disease_catalog). Korean + English phenotype labels let the Planning Team
-- slice in Korean without a translation step (D-10 rationale).
--
-- The scoring engine emits 44 disease ids; the 9 extras (macular degeneration,
-- brain aneurysm, cardiac arrhythmia, endometrial cancer, endometriosis,
-- hepatocellular carcinoma, lung cancer, Parkinson's, PCOS) are scored but not
-- shown to users, and are deliberately NOT in this dim (owner decision
-- 2026-08-06). fct_user_disease_day keeps their rows and flags them with
-- is_in_catalog = false, so the dim stays the user-facing 35 while the fact
-- stays complete. Any disease-sliced metric view must join this dim (or filter
-- is_in_catalog) rather than reading the fact raw.

select
	disease_id,
	phenotype_kor,
	phenotype_eng
from {{ ref('irs_disease_catalog') }}

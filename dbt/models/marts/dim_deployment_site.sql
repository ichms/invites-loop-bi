-- Grain: one row per deployment site.
--
-- One row today, built anyway (D-10): the portability matrix is a claim about
-- four sites, and if the model cannot express "which site", the claim is a
-- slide rather than something the warehouse can test. That reason still holds.
--
-- ============================================================================
-- CORRECTED 2026-08-10. This header used to end: "When Jeju / GRMC / Shenzhen
-- become real, they arrive as rows here and as a populated dim_user.site_id —
-- no restructuring." Both halves of that were wrong.
-- ============================================================================
--
-- 1. RESTRUCTURING IS REQUIRED. The owner's Jeju requirement is "this person was
--    in Ulsan and is now ALSO in Jeju" — one user, two live affiliations. A
--    scalar dim_user.site_id cannot hold two values, and dim_user is SCD Type 1
--    (D-08), so writing Jeju over Ulsan would silently re-attribute every
--    historical fact for that user. What this needs is a bridge at
--    (user_id, site_id, valid_from, valid_to), not a populated column.
--
-- 2. A SOURCE SYSTEM DOES CARRY SITE IDENTIFIERS, and did when the old note
--    claimed otherwise. `ichms.auth_customer` holds 울산 and 제주 as rows, and
--    `ichms.auth_user_customer` links users to them — already a temporal bridge
--    (surrogate PK, NO unique constraint on user_id, linked_dt / unlinked_dt).
--    Both are already landed in stg_ichms. Measured 2026-08-10: all 404
--    dim_user users join to it and every one resolves to ULSAN; JEJU exists with
--    14 linked users, none of them in the sibc cohort.
--
-- STILL HARDCODED ON PURPOSE. This model is not yet sourced from
-- stg_ichms.auth_customer because that table conflates deployment sites (울산,
-- 제주) with application tenants (LIS, 아이콜리, iCHMS Operator/Expert/Customer
-- Web). Selecting from it naively would publish "LIS" as a deployment site.
-- Which customers are sites is an owner rule, not something to infer here, so
-- the placeholder stays until that rule exists — see CLAUDE.md § "Site
-- affiliation is multi-valued" and todo.md B0 for the open questions.
--
-- OPEN (owner): `site_id` below is a placeholder code for the current Korean
-- Loop pilot cohort. Confirm the official code/name before this reaches a
-- dashboard label.

select
	'KR_LOOP_PILOT' as site_id,
	'Invites Loop 파일럿 (한국)' as site_name_kor,
	'Invites Loop pilot (Korea)' as site_name_eng,
	'KR' as country_code

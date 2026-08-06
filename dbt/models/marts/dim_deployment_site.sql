-- Grain: one row per deployment site.
--
-- One row today, built anyway (D-10): the portability matrix is a claim about
-- four sites, and if the model cannot express "which site", the claim is a
-- slide rather than something the warehouse can test. When Jeju / GRMC /
-- Shenzhen become real, they arrive as rows here and as a populated
-- dim_user.site_id — no restructuring.
--
-- OPEN (owner): `site_id` below is a placeholder code for the current Korean
-- Loop pilot cohort; no source system carries a site identifier yet, so every
-- user is assigned to it in dim_user. Confirm the official code/name before
-- this reaches a dashboard label.

select
	'KR_LOOP_PILOT' as site_id,
	'Invites Loop 파일럿 (한국)' as site_name_kor,
	'Invites Loop pilot (Korea)' as site_name_eng,
	'KR' as country_code

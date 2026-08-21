-- GRAIN: one user × analysis day. This canonical fact keeps the dense panel
-- from reaching back into staging and preserves the allow-listed signatures
-- without exposing the source JSONB payload.

select
	i.user_id,
	i.ymd_date,
	i.signature_description,
	i.signature_disease_type_code,
	i.signature_disease_type_label,
	i.signature_lifestyle_type_code,
	i.signature_lifestyle_type_label,
	i.signature_potential_type_code,
	i.signature_potential_type_label,
	i.signature_segment_type_code,
	i.signature_segment_type_label
from {{ ref('stg_sibc__user_intg_log') }} as i
inner join {{ ref('dim_user') }} as u using (user_id)

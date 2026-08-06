-- The glucose unit-normalisation rule in stg_discovery__lifelog_measurements
-- reads a gap, not a guess: everything below 30 is treated as mmol/L and
-- converted to mg/dL (×18.0182). That is safe only while the two populations
-- stay well separated — today the highest mmol/L reading is 6.94 and the lowest
-- mg/dL reading is 68, so the threshold sits in a wide empty band.
--
-- A reading in 25–50 would be genuinely ambiguous: 30 could be 30 mg/dL (severe
-- hypoglycaemia) or 30 mmol/L (540 mg/dL, severe hyperglycaemia) — opposite
-- clinical emergencies from the same number. The rule would silently pick one.
--
-- This fails the build rather than warning: which reading is right is a
-- clinical question, and a wrong answer here is a wrong number about a
-- medical emergency. The fix is a per-row unit from the source, not a wider
-- threshold.

select
	user_lifelog_sn,
	measured_dt,
	glucose as ambiguous_raw_value
from {{ source('stg_discovery', 'disc_lifelog_user_bloodglucose') }}
where glucose::numeric >= 25
	and glucose::numeric <= 50

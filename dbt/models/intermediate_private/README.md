# Private physical intermediates

Reusable high-cost deduplication and aggregation relations live here. dbt
materializes them in `intermediate_private`; general BI and Superset roles have
no schema or relation privileges.

The historically named `stg_discovery__lifelog_wearable_day` was moved here in
P2 without changing its model name. P4 added the physical
`stg_discovery__lifelog_wearable_heartrate` dedupe and changed the daily,
detail, attribution, and reconciliation paths to reuse it. Both physical models
replace a bounded 30-day event-time window; corrections outside that boundary
require an explicit measured full refresh.

# Private physical intermediates

Reusable high-cost deduplication and aggregation relations live here. dbt
materializes them in `intermediate_private`; general BI and Superset roles have
no schema or relation privileges.

The historically named `stg_discovery__lifelog_wearable_day` is already a
physical aggregate and is moved here in P2 without changing its model name.
P4 adds the reusable heart-rate dedupe relation and makes both core and detail
consumers use it.

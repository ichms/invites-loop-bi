# marts — dims, facts and metric views (tables/views in the `marts` schema)

The only schema the Metabase read-only role (`bi_reader`) is granted. Every
fact declares its grain in a header comment and enforces it with a
`dbt_utils.unique_combination_of_columns` test — the grain tests are the one
thing that must never be cut (decision log §2.6).

Metric views live here too, one metric per view, tier prefix mandatory:
`v_kpi_*` / `v_pi_*` / `v_bridge_*` (D-10). The KPI / PI / Bridge separation
is load-bearing; do not conflate the tiers.

# marts — dims, facts and metric views (tables/views in the `marts` schema)

The only schema the Superset read-only role (`superset_reader`) is granted. Every
fact declares its grain in a header comment and enforces it with a
`dbt_utils.unique_combination_of_columns` test — the grain tests are the one
thing that must never be cut (decision log §2.6).

Metric views live here too, one metric per view, tier prefix mandatory:
`v_kpi_*` / `v_pi_*` / `v_bridge_*` (D-10). The KPI / PI / Bridge separation
is load-bearing; do not conflate the tiers.

## `fct_user_day` is dense — read this before editing it

It is not a fact of things that happened. It is a **panel**: every user-day from
the earlier of enrolment and first observed activity, up to the observation
frontier, including days with nothing on them (D-29). Zero is a measurement, not
a missing value, because **the zero days are the denominator** — an only-active
spine divides by the wrong number and biases every behavioural rate upward.

Three rules that follow:

1. **The upper bound is the observation frontier, never `current_date`** (D-30).
   Extending to today invents zero-activity days for dates the ELT has not
   loaded, which renders as a product collapse.
2. **The lower bound is not `joined_dt`.** App usage predates study enrolment for
   some users, and the pre-enrolment window is what makes a pre-period
   available. `days_since_joined` is negative there, deliberately.
3. **Never compute a rate without its denominator column in the same row.**
   `routines_completed` / `routines_delivered` are a pair for this reason.

`../../tests/assert_user_day_spine_loses_no_activity.sql` asserts the fact's
per-channel totals equal staging's. The spine is bounded, so anything outside it
disappears **silently** — grain and `not_null` tests all still pass. That test
caught 381 dropped meal records on the first attempt. Do not delete it.

## `fct_wearable_day` is sparse intensity

Wear-day presence stays on `fct_user_day.wearable_streams_active`. This fact
holds the daily values (step count, sleep hours, HR mean/min/max, SpO2, activity
kcal). A NULL column means that stream did not fire — do not coalesce it to 0
on the dense panel. Heart-rate samples are pre-aggregated; they are not in
`fct_measurement`.

## Raw wearable observations are source-shaped

`fct_wearable_step`, `fct_wearable_activity`, `fct_wearable_heartrate`,
`fct_wearable_oxygen_saturation`, `fct_wearable_sleep` and
`fct_wearable_sleep_stage` preserve the six source grains. They are separate
facts because a point sample, an activity interval and a sleep session do not
share one honest compound grain. Use these for observation-level work; use
`fct_wearable_day` for routine daily intensity reporting.

Exact duplicate source payloads collapse to one `observation_id`, but
`source_row_count` preserves their multiplicity. Sum that column when the
question is about delivered source rows; count fact rows when the question is
about distinct observations. Wearable backfill still applies, so quote either
count with its extraction date.

## Wide datasets

`fct_user_day_wide` is the panel with Frame 2 segment columns (`sex`,
`bmi_band`, `cohort_group`, `is_observable_*`) and calendar helpers already
joined. Prefer it in Superset for multi-angle behavioural charts; keep
`fct_user_day` as the thin fact the metric views and notebooks compose over.

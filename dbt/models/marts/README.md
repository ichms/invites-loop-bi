# marts — dims, facts and metric views (tables/views in the `marts` schema)

The only schema the Metabase read-only role (`bi_reader`) is granted. Every
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

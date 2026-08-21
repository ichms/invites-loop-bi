# dbt staging layer

This directory contains dbt models that standardise the EL landing schemas
before data enters a mart. The landing schemas and the dbt staging schema are
different layers:

| Layer | Names | Writer | Purpose |
|---|---|---|---|
| EL landing | `stg_iccoli`, `stg_sibc`, `stg_ichms`, `stg_irs`, `stg_discovery` | Extract/load pipelines | Minimised copies of source tables plus `_loaded_at` |
| dbt staging | `staging` | dbt | Casts, deduplication, key translation, PII blocking, and source-specific normalization |

Files follow `stg_<system>__<source_table>.sql`. Landing relations are declared
as dbt sources in `src_<system>.yml`; dbt never writes back to a landing schema.

## Current state — 2026-08-21

P0 through P4 are complete. The search/share landing contract, dbt sources,
PII-safe staging models, actor translation, grain/FK tests, and dynamic
reconciliation are implemented and green. P4 moved the heart-rate model to a
physical 30-day window-replace relation in `intermediate_private`; the daily,
detail, attribution, and reconciliation paths now `ref()` it. The obsolete
staging view was removed after a zero-dependency check.

Do not describe the current graph as the completed P2–P4 target. Mutable row counts,
especially wearable counts, must always include their extraction date.

## Layer contract

Staging is the last place where a source-shaped key or payload may be handled.
Every model must make the downstream contract explicit:

1. Declare its grain and enforce the grain with a uniqueness test.
2. Cast source strings to stable warehouse types and preserve the original
   event timestamp.
3. Derive business dates explicitly on the `Asia/Seoul` boundary rather than
   relying on the session timezone.
4. Translate source user serials to the mart `user_id` through the Loop mapper.
   Source serials must not leave staging.
5. Deduplicate only according to a measured source contract. Do not merge rows
   across source systems merely because their payloads look similar.
6. Reconcile source rows, mapped rows, excluded rows, and fact rows without
   pinning a mutable production count as a permanent constant.
7. Keep landing and channel freshness visible. An empty incremental extraction
   does not, by itself, prove that an entire source DAG completed successfully.

Existing examples include last-write selection for the SiBC daily analysis
logs, `ymd` string-to-date casts, Loop mapper joins for iccoli activity, and
allow-listed JSONB flattening. Those mechanisms remain useful, but they are not
authority for a new source without a measured grain and reconciliation.

## P1 search and share contract

P1 added these models after P0 made the landing extraction full-refresh and
PII-safe:

- `stg_iccoli__tb_search_log`
- `stg_iccoli__tb_share_info`
- `stg_iccoli__tb_share_log`

They translate `user_no` or `from_user_no` to Loop `user_id`, retain the
source event timestamp and an explicit KST business date, and omit raw source
serials from their outputs. Tests cover measured source unique-index grain, actor
mapping, the `share_no` relationship, sender consistency, and source-to-staging
reconciliation.

The three share denominators are distinct and must remain reconstructible:

- share links created (`share_info` rows);
- share links with at least one interaction (distinct interacted `share_no`);
- share interaction events (`share_log` rows).

`tb_share_log` is a neutral interaction signal until its business meaning is
confirmed. It must not be described as an open, success, or sender action, and
it must not make the sender active on a day by default.

## PII boundary

PII minimisation begins at extraction; staging is a second enforcement point,
not a substitute for it. The following fields must not appear in dbt staging or
general marts:

- search free text (`tb_search_log.word`);
- share tokens (`share_key`);
- recipient IP and user-agent;
- external recipient serials (`to_user_no`).

Polymorphic `target_no` is a separate restricted field: it may identify a user
for some `share_type` values. It must not enter a general mart until each type
has an approved PII and FK contract. If it is temporarily retained in a
restricted staging relation, it is not an approved user key or general join
field.

Direct identifiers, free text, access tokens, device fingerprints, and
unnecessary external user keys are excluded by default. Existing reductions,
such as exposing only `birth_year` instead of raw birth data, follow the same
rule. See [`PII_INVENTORY.md`](../../../PII_INVENTORY.md) for the inventory;
the target configuration and inventory must agree before P0 is complete.

## P4 wearable processing contract

The daily core and observation-detail paths reuse one physical,
deduplicated heart-rate relation. That relation must:

- calculate the expensive payload deduplication once;
- preserve duplicate multiplicity as `source_row_count`;
- keep `n_samples = sum(source_row_count)`;
- reproduce multiplicity-weighted mean, min, max, and daily aggregates;
- use a 30-day lookback or equivalent window-replace strategy; and
- retain an explicit, monitored full-refresh path for older corrections.

Reusable intermediates belong in a schema that general BI roles cannot read.
Source-grain wearable facts belong in `marts_detail`, not the daily core or the
general Superset role. The expensive full-source equivalence test is tagged
`p4_heartrate_audit` and excluded from routine selectors. It passed after both
full refresh and incremental replacement on 2026-08-21.

## Build gates

During P4–P5, only exact, reviewed small-model selections may be built after
inspecting the selected graph. Any selection that reaches raw heart-rate or
wearable detail is out of scope for an ordinary targeted build.

The first complete core build is P6. It requires all of the following:

- required source freshness passes as a hard gate;
- the `daily_core` selector excludes wearable detail;
- Azure Monitor reports storage below the stop line;
- execution uses one thread and fail-fast; and
- grain, FK, PII, freshness, and reconciliation tests are included in the
  selected graph.

See the [marts layer guide](../marts/README.md) for the downstream contract.

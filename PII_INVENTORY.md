# PII Inventory and Retention Contract

**Structural snapshot:** 2026-08-21 KST

**Scope:** all base tables currently present in the five `stg_<system>` landing schemas

**Status:** P0 search/share EL policy, landing cleanup, inventory reconciliation, and offline
verification complete

This document contains classifications and counts, never identifier values. Current measured
facts and [`todo.md`](todo.md) override historical notes. An excluded source column is a
policy boundary; restoring it requires owner approval, not merely a config edit.

## 1. What was verified

A read-only `information_schema` inspection of `invites_dw` produced:

| Landing schema | Base tables | Columns including `_loaded_at` |
|---|---:|---:|
| `stg_iccoli` | 37 | 443 |
| `stg_ichms` | 16 | 126 |
| `stg_sibc` | 36 | 401 |
| `stg_irs` | 5 | 47 |
| `stg_discovery` | 34 | 235 |
| **Total** | **128** | **1,252** |

The table counts match the 2026-08-21 extraction target registry. The column count is a
structural snapshot, not proof that every JSON value or free-text payload is classified.

All 128 watermark records were `SUCCESS` at inspection time. That status means the last
recorded table load succeeded; it does not prove whole-DAG completion, per-channel freshness,
or PII compliance.

## 2. Classification scheme

| Class | Meaning | Default treatment |
|---|---|---|
| Direct identifier | Identifies or contacts a person: name, phone, email, login ID, IP, chart number | Exclude at EL |
| Credential or access secret | Password hash, session/device/push token, share key, redeemable secret | Exclude at EL; clean existing landing |
| Fingerprint | User-agent and device combinations that can single out a person | Exclude unless an approved purpose requires it |
| Quasi-identifier | Identifying in combination: birth data, age, sex, site, anthropometrics, family/referral links | Minimize and apply small-cell rules |
| Sensitive content | Clinical/genomic data, health narrative, chat, survey free text, prescription or consultation payload | Purpose- and role-restricted; never expose raw to general BI |
| Linkage key | Pseudonymous analytical key such as `user_id`, source serial, parent/event ID | Keep only where the grain or reconciliation requires it |
| Analytical/meta | Measures, controlled codes, flags, timestamps, and `_loaded_at` | Keep subject to purpose and grain |

“Pseudonymous” does not mean anonymous. A `user_id` remains linkable to a person through
source systems and must stay inside the approved analytical boundary.

## 3. Search/share P0 closure

The three new iccoli tables were landed before their final exclusion contract. The current
landing structure and non-null counts were measured on 2026-08-21.

| Table.column | Classification | Current landing | Required P0 treatment |
|---|---|---:|---|
| `tb_search_log.word` | User-entered free text | Removed; 514 / 514 populated before cleanup | Excluded before COPY |
| `tb_share_info.share_key` | Access-token-like unique key | Removed; 1,141 / 1,141 before cleanup | Excluded before COPY |
| `tb_share_log.share_key` | Access-token-like unique key | Removed; 572 / 572 before cleanup | Excluded before COPY |
| `tb_share_log.to_user_ip` | Direct network identifier | Never present in measured landing | Excluded before COPY |
| `tb_share_log.to_user_agent` | Fingerprint | Removed; 572 / 572 before cleanup | Excluded before COPY |
| `tb_share_log.to_user_no` | External/non-Loop recipient key | Removed; 572 / 572 before cleanup | Excluded before COPY |
| `tb_share_info.target_no` | Polymorphic key; may be a user key for some `share_type` values | Present; source `NOT NULL`, landing nullable | Do not expose to general marts until a per-type PII and FK contract exists |

The actor keys `user_no` and `from_user_no` are needed only to translate the Loop actor to
`user_id`. Raw actor serials must not survive dbt staging. `share_no`,
`search_log_no`, and `share_log_no` remain as source-grain identifiers where required for
facts and reconciliation.

The target config excludes every prohibited field and declares all three tables as filtered
full refresh. The separately reviewed `scripts/20260821_search_share_pii_cleanup.sql`
migration removed the already-landed copies on 2026-08-21. Its dependency preflight returned
zero rows, its transaction postcondition passed, and a post-cleanup catalog query returned
zero prohibited columns. The three table row and actor counts were unchanged.

### 3.1 Source physical contract

Read-only source catalog and aggregate checks at 2026-08-21 11:32 KST found:

| Table | Source-declared PK | Unique grain index | All / Loop-filtered rows | Observed updates | Time contract |
|---|---|---|---:|---:|---|
| `tb_search_log` | none | `search_log_no` | 1,133 / 518 | 14 | `create_datetime timestamptz`, source `NOT NULL` |
| `tb_share_info` | none | `share_no` | 1,816 / 1,142 | 0 | `create_datetime timestamptz`, source `NOT NULL` |
| `tb_share_log` | none | `share_log_no` | 1,018 / 573 | 28 | `create_datetime timestamptz`, source `NOT NULL` |

The three indexed grain candidates were unique in the measured data. The loader reads only
catalog-declared primary keys, so it correctly treats these sources as keyless. Update counts
come from PostgreSQL statistics at the stated time and can change; they prove mutation
behavior but are not row-count test constants. Both source and warehouse sessions used
`Asia/Seoul`.

## 4. Existing EL controls

The following controls are already represented in target configuration and historical cleanup
migrations. This is a category summary; config is the executable source of truth.

| Source | Existing control |
|---|---|
| iccoli identity/profile | CI/DI, names, contact fields, login identifiers, nicknames, introductions, and device/push tokens are excluded where configured |
| iccoli cohort scope | Analytical and user-event tables use a source-side Loop actor filter; the deliberately unfiltered mapper defines/translates the cohort and is not an analytical target |
| iccoli search/share | Filtered full refresh; search text, share keys, recipient IP/user-agent, and external recipient key are excluded before COPY |
| sibc | Relational names and full birth date/time fields are excluded; dbt selects only approved analytical columns |
| ichms | Password hashes, login IDs, phone, login IP/token IDs, names, birth data, chart number, profile image URL, family name, and family message text are excluded |
| discovery | Large raw lifelog payloads not required for attribution or facts are excluded where configured |
| JSONB | dbt extraction uses an allow-list plus drift tests; known identity keys remain unselected |

The migrations in `scripts/20260806_pii_cleanup.sql` and
`scripts/20260806_pii_cleanup_phase1.sql` record earlier cleanup. They were executed in
2026-08-06 conditions and must not be rerun blindly. The separately reviewed
`scripts/20260821_search_share_pii_cleanup.sql` records the P0 search/share cleanup and its
postconditions.

## 5. Retained sensitive scopes requiring policy ownership

Landing is not a general BI surface, but retention there still affects warehouse access and
backups. These scopes remain policy questions.

| Scope | Why it is sensitive | Current safe posture | Owner decision needed |
|---|---|---|---|
| iCHMS `auth_*` and `mem_*` tables | Identity/account/family domain; not cohort-filtered | Keep direct-column exclusions; no general mart exposure | Whether unused tables belong in the warehouse at all |
| IRS `job_input_data` | Genomic and medical/profile/lifestyle payloads | No raw general mart exposure | Purpose, retention period, and restricted role |
| Discovery consultation/examination/medical/prescription/genomic tables | Clinical, prescription, and genomic payloads | No raw general mart exposure | Which tables are required and for how long |
| SiBC chat, narrative, profile, and operational payloads | Health narrative and potentially free text | Explicit dbt projection/allow-list only | Purpose and retention for unused landing payloads |
| Search terms | User free text | Exclude at EL | Reintroduction only after approved taxonomy, role, and retention plan |
| External share recipients | Non-cohort linkage | Do not retain raw recipient keys | Whether any aggregate recipient analysis has a lawful purpose |

Until an owner answers, the safe default is minimization and no public metric depending on the
field.

## 6. Defense in depth

No single control is “the PII boundary.” The contract is layered:

1. **Source target selection:** do not extract unnecessary tables.
2. **EL column exclusion:** direct identifiers, secrets, fingerprints, and unapproved free
   text must not leave the source. The search/share fields in §3 are now excluded.
3. **EL row filtering:** cohort-scoped iccoli tables extract Loop actors only.
4. **dbt staging projection:** translate source keys, flatten only allowed JSON keys, and
   omit raw prohibited fields.
5. **Mart contracts:** expose only `user_id` and the minimum attributes required by a
   measured use case.
6. **Schema grants:** general BI reads `marts` only; future `marts_detail`, private
   intermediates, staging, and landing are denied.
7. **Metric controls:** eligibility, small-cell behavior, evidence status, and
   `data_as_of` constrain publication.
8. **Backup and credential controls:** landing and Superset metadata backups inherit the
   sensitivity of their contents.

An empty mart does not prove the pipeline is safe, and a read-only database role does not
repair over-retention upstream.

## 7. Structural risks and mandatory review triggers

- The loader automatically adds new upstream columns. An identity field can therefore land
  unless target review catches it.
- JSONB can add keys without relational schema change. Allow-list drift tests detect known
  payloads only where attached.
- A full-refresh load propagates source deletions, but it does not remove a landing column
  merely because `exclude_columns` changed.
- A source-side cohort filter can miss pre-enrollment history when a user becomes eligible
  after the watermark. Any replay procedure requires a reviewed operating contract; manual
  watermark deletion is prohibited during P0–P5.
- General-purpose source keys can change meaning by subtype. `target_no` must not be
  modeled as a user FK by guesswork.

Re-run this inventory whenever:

- an extraction target is added or removed;
- `exclude_columns` or `row_filter` changes;
- the loader reports an added source column;
- a JSONB drift test reports a new key;
- a new mart or database role is proposed;
- a cleanup migration changes landing structure.

## 8. P0 completion evidence

P0 can mark the PII work complete only when all of the following are reviewable:

- the three new iccoli tables are full-refresh targets with Loop actor filters;
- all prohibited search/share columns are excluded in config and pinned by tests;
- existing landing columns are removed by a separate reviewed cleanup migration;
- pre/post cleanup queries show no downstream dependency and no prohibited column;
- the target registry and this 128-table inventory reconcile;
- offline Python tests pass.

Current status: **complete for P0**. The post-cleanup inventory contains 128 landing tables
and 1,252 columns, the target registry has the intended 37/16/36/5/34 split, the prohibited
catalog query returns zero rows, and the offline suite passes at 95 passed / 32 skipped.

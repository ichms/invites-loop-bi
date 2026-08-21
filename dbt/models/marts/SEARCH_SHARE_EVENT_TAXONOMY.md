# Search/share event taxonomy

Measured at the 2026-08-21 08:58 KST landing snapshot. Counts are evidence for
this extraction only and are not test constants.

| Relation | Grain | Meaning | Current retained-cohort rows |
|---|---|---|---:|
| `fct_app_search_event` | `search_log_no` | Search event without query text | 487 expected |
| `fct_share_link` | `share_no` | Share link/object creation | 1,131 expected |
| `fct_share_interaction_event` | `share_log_no` | Neutral downstream interaction candidate | 561 expected |

The expected rows are the P0 landing rows intersected with the current SiBC
cohort. Landing-to-staging mapping loses no rows. Mapper-only actors explain the
dynamic staging-to-fact difference: 27 search rows, 10 share-link rows, and 11
interaction rows at this snapshot. Tests recompute those differences rather
than pinning the numbers above.

## Three different share denominators

- Share links created: `count(*)` from `fct_share_link`.
- Interacted links: `count(distinct share_no)` from
  `fct_share_interaction_event`.
- Interaction events: `count(*)` from `fct_share_interaction_event`.

At the landing snapshot there were 1,141 links, 181 interacted links, and 572
interaction events before current-cohort fact filtering. These values are not
interchangeable and must never share one label such as “shares.”

## Relationship to existing app actions

`fct_app_action` already has source action categories POST/SHARE and
SURVEY/SHARE. The same landing snapshot contained 159 POST/SHARE action events
and 116 SURVEY/SHARE action events. `tb_share_info` contained 524 POST and 275
SURVEY link rows.

The sources expose no approved row-level key that proves an action row and a
share-link row are the same business event. Therefore:

- retain both source-shaped facts;
- do not add their counts;
- do not cross-source deduplicate by actor or timestamp proximity;
- define any future combined active-event taxonomy as a versioned metric
  contract with an explicit precedence rule.

`tb_share_log.point_call_yn` remains `source_point_call_yn`. Its exact write
meaning is not confirmed, so neither value is called an open or success. A
share interaction also does not make the mapped sender active by default.

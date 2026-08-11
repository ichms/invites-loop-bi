# metrics — canonical metric definitions (views in `marts`)

One metric per view, tier encoded in the prefix (D-10). The prefix is not
decoration: conflating the tiers is the known failure mode this structure
exists to prevent.

| Prefix | Tier | Meaning |
|---|---|---|
| `v_kpi_` | KPI | Headline outcome the organisation is judged on |
| `v_pi_` | PI | Performance indicator — measurable, and believed to move the KPI |
| `v_bridge_` | Bridge | The link between a PI and a KPI, including what is missing |

## Why there are no `v_kpi_*` views

The headline KPIs in the business documents — 30-day readmission rate, length
of stay, MSPB, Self-Pay Bad Debt, VBC incentives — are **hospital-financial
measures with zero source tables in this estate**. There is no admission,
discharge, claim or billing data anywhere in the warehouse.

Building them as views returning NULL was rejected (Q-08, and the log's §4.5):
a dashboard full of NULLs erodes trust in the dashboards that *are* real, and a
KPI that always reads zero is worse than an absent one because someone will
eventually cite it.

So the KPI tier is deliberately empty, and `v_bridge_pi_to_kpi` documents each
missing KPI, the PI standing in for it today, and what data would have to exist
to compute it. When that data arrives, a `v_kpi_*` view is added here and the
bridge row is updated — the register is the to-do list.

## Adding a metric

See `deploy/superset/METRICS.ko.md`. In short:
edit or add a view here, `dbt build`, open a PR. A metric definition changes in
git, under review — never by someone editing SQL inside a dashboard card, which
is why native SQL is switched off for the Planning Team (D-17).

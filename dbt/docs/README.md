# dbt documentation (committed HTML)

`dbt_docs.html` is the generated dbt documentation site — model descriptions,
column-level docs, test coverage and the full lineage graph — as **one
self-contained file**. Open it in a browser; nothing needs to be running.

This is the answer to Q-07 ("where do dbt docs get hosted"): in the repo the
junior already has. No hosting, no URL to expire, no service to own — and it is
diffable in the sense that matters (it is regenerated, not hand-edited).

## Regenerating

Run after any model, test or description change, then commit the result:

```bash
source setup_env.sh
uv run dbt docs generate --project-dir dbt --static
cp dbt/target/static_index.html dbt/docs/dbt_docs.html
```

`--static` is what produces the single-file build; without it dbt writes a
directory of assets that needs a web server.

Note: `dbt/target/` is gitignored (build output), which is why the file is
copied here rather than committed in place.

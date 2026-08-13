# dbt documentation

Generate a self-contained HTML site — model descriptions, column-level docs,
test coverage and the full lineage graph — and open it in a browser. Nothing
needs to be running, and the file is not committed.

```bash
source setup_env.sh
uv run dbt docs generate --project-dir dbt --static
```

Open `dbt/target/static_index.html`. `--static` is what produces the
single-file build; without it dbt writes a directory of assets that needs a
web server. `dbt/target/` is gitignored.

This is the answer to Q-07 ("where do dbt docs get hosted"): generate them
locally from the models already in the repo. No hosting, no URL to expire,
no generated HTML in git.

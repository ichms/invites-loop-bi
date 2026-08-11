#!/bin/bash
# Register every marts relation as a Superset dataset, via the REST API.
# Run from deploy/superset/ on the host, after the stack is healthy:
#
#   ./scripts/register_marts_datasets.sh
#
# Idempotent: relations that already have a dataset are skipped. New dbt
# models need this re-run (or a click in the UI) — Superset does not
# schema-sync; datasets are explicit objects.
set -euo pipefail
cd "$(dirname "$0")/.."
source .env

BASE="http://localhost:${SS_HOST_PORT:-8088}"
COOKIES="$(mktemp)"
trap 'rm -f "$COOKIES"' EXIT

# The table list comes from the warehouse itself (read-only), so this script
# has exactly one source of truth for "what exists in marts".
TABLES=$(PGPASSWORD="$SS_DW_PASSWORD" psql \
	"host=$SS_DW_HOST port=$SS_DW_PORT dbname=$SS_DW_DBNAME user=$SS_DW_USER" \
	-Atc "SELECT c.relname FROM pg_class c
	      JOIN pg_namespace n ON n.oid = c.relnamespace
	      WHERE n.nspname = 'marts' AND c.relkind IN ('r','v','m')
	      ORDER BY 1")

TOKEN=$(curl -sf "$BASE/api/v1/security/login" -H 'Content-Type: application/json' \
	-d "{\"username\":\"$SS_ADMIN_USER\",\"password\":\"$SS_ADMIN_PASSWORD\",\"provider\":\"db\",\"refresh\":false}" \
	| python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

CSRF=$(curl -sf "$BASE/api/v1/security/csrf_token/" -H "Authorization: Bearer $TOKEN" \
	-c "$COOKIES" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"])')

DB_ID=$(curl -sf "$BASE/api/v1/database/" -H "Authorization: Bearer $TOKEN" \
	| python3 -c 'import json,sys
d=json.load(sys.stdin)
ids=[r["id"] for r in d["result"] if r["database_name"]=="invites_dw"]
print(ids[0] if ids else "")')
[[ -n "$DB_ID" ]] || { echo "database 'invites_dw' not registered in Superset — run the init service first"; exit 1; }

for t in $TABLES; do
	body=$(printf '{"database":%s,"schema":"marts","table_name":"%s"}' "$DB_ID" "$t")
	out=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/v1/dataset/" \
		-H "Authorization: Bearer $TOKEN" -H "X-CSRFToken: $CSRF" \
		-H 'Content-Type: application/json' -b "$COOKIES" -d "$body")
	case "$out" in
		201) echo "created  marts.$t" ;;
		422) echo "exists   marts.$t" ;;
		*)   echo "FAILED   marts.$t (HTTP $out)"; exit 1 ;;
	esac
done

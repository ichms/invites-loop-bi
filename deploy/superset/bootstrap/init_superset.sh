#!/bin/bash
# One-shot bootstrap, run by the superset-init service before the server
# starts. Every step is idempotent, so this runs on every `docker compose up`.
#
# This is the part Metabase OSS cannot do: the warehouse connection is
# registered from configuration, not clicked into an admin UI.
set -euo pipefail

echo "==> superset db upgrade (app-DB migrations)"
superset db upgrade

echo "==> ensure admin user"
# create-admin exits non-zero if the user exists; that is the idempotent path.
superset fab create-admin \
	--username "${SS_ADMIN_USER}" \
	--firstname Admin \
	--lastname "${SS_ADMIN_USER}" \
	--email "${SS_ADMIN_EMAIL}" \
	--password "${SS_ADMIN_PASSWORD}" \
	|| echo "    admin user already exists, leaving it in place"

echo "==> superset init (default roles and permissions)"
superset init

if [[ -n "${SS_DW_HOST}" && -n "${SS_DW_PASSWORD}" ]]; then
	echo "==> register warehouse connection 'invites_dw' (marts via superset_reader)"
	superset set-database-uri \
		--database-name invites_dw \
		--uri "postgresql+psycopg2://${SS_DW_USER}:${SS_DW_PASSWORD}@${SS_DW_HOST}:${SS_DW_PORT}/${SS_DW_DBNAME}"
else
	echo "==> SS_DW_HOST / SS_DW_PASSWORD not set — skipping warehouse registration"
fi

echo "==> bootstrap complete"

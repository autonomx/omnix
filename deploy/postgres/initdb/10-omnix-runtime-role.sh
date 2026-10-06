#!/bin/sh
# Creates the runtime role on a new database volume (WP-11.2). Migrations run as
# the owner (POSTGRES_USER) and grant this role data access; it is not a
# superuser, not the owner and has no BYPASSRLS, so row-level security applies.
set -eu
: "${OMNIX_APP_DB_PASSWORD:?OMNIX_APP_DB_PASSWORD is required}"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set=app_password="$OMNIX_APP_DB_PASSWORD" <<'SQL'
CREATE ROLE omnix_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD :'app_password';
GRANT CONNECT ON DATABASE :"DBNAME" TO omnix_app;
SQL

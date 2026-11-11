#!/bin/sh
set -eu
# Only executed on an EMPTY PostgreSQL data volume, by the official image's entrypoint.
# Application/migration owner is a separate non-superuser role.
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=ON_ERROR_STOP=1 --set=app_user="$APP_DB_USER" \
  --set=app_password="$(cat /run/secrets/db_password)" --set=db_name="$POSTGRES_DB" <<'SQL'
CREATE ROLE :"app_user" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_password';
GRANT CONNECT ON DATABASE :"db_name" TO :"app_user";
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO :"app_user";
SQL

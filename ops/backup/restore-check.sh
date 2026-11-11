#!/bin/sh
set -eu
export PGPASSWORD="$(cat "$PGPASSWORD_FILE")"
file="${1:?Pass the basename of a finalized .dump file from /backups}"
case "$file" in *[!a-zA-Z0-9._-]*|'') echo 'Expected a backup basename, no directory' >&2; exit 1;; esac
case "$file" in istay-*.dump) ;; *) echo 'Expected istay-*.dump' >&2; exit 1;; esac
client_id="${2:-}"
payload_hash="${3:-}"
if [ -n "$client_id" ]; then
  case "$client_id" in *[!a-fA-F0-9-]*) echo 'Invalid expected inspection UUID' >&2; exit 1;; esac
  case "$payload_hash" in *[!a-fA-F0-9]*|'') echo 'Invalid expected payload hash' >&2; exit 1;; esac
  [ "${#client_id}" -eq 36 ] && [ "${#payload_hash}" -eq 64 ] || exit 1
fi
cd /backups
sha256sum -c "$file.sha256"
scratch="istay_restore_$(date -u +%Y%m%d%H%M%S)_$$"
[ "$scratch" != "$PGDATABASE" ]
# Destructive cleanup is limited to this freshly generated temporary database.
createdb --maintenance-db=postgres "$scratch"
trap 'dropdb --maintenance-db=postgres --if-exists "$scratch"' EXIT INT TERM
pg_restore --exit-on-error --no-owner --no-acl --dbname="$scratch" "$file"
psql --dbname="$scratch" --set=ON_ERROR_STOP=1 --command='SELECT version_num FROM alembic_version; SELECT count(*) AS sites FROM sites; SELECT count(*) AS telcos FROM telcos; SELECT count(*) AS users FROM users; SELECT count(*) AS inspections FROM inspection_records;'
if [ -n "$client_id" ]; then
  restored="$(psql -X --dbname="$scratch" --set=ON_ERROR_STOP=1 --set=client_id="$client_id" --set=payload_hash="$payload_hash" -At <<'SQL'
SELECT 'BUSINESS_RECORD_JSON ' || json_build_object('client_id', r.client_id, 'payload_hash', r.payload_hash,
  'outcome', r.outcome, 'user_id', r.user_id, 'target_id', r.target_id,
  'measurement', CASE WHEN m.inspection_id IS NULL THEN NULL ELSE json_build_object(
    'download_mbps',m.download_mbps,'upload_mbps',m.upload_mbps,'ping_ms',m.ping_ms,
    'engine_version',m.engine_version,'profile_version',m.profile_version) END,
  'snapshot', t.location_snapshot, 'audit_status', a.status)::text
FROM inspection_records r LEFT JOIN speed_measurements m ON m.inspection_id=r.id
JOIN audit_targets t ON t.id=r.target_id JOIN audits a ON a.id=t.audit_id
WHERE r.client_id=:'client_id' AND r.payload_hash=:'payload_hash';
SQL
)"
  [ -n "$restored" ] || { echo 'Expected business inspection/hash missing from restored database' >&2; exit 1; }
  printf '%s\n' "$restored"
fi
echo 'Restore completed in an isolated scratch database; live database was not replaced.'

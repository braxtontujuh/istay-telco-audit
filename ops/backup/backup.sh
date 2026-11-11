#!/bin/sh
set -eu
umask 077
case "${RETENTION_DAYS:-30}" in ''|*[!0-9]*) echo 'Invalid retention' >&2; exit 1;; esac
[ "${RETENTION_DAYS:-30}" -ge 1 ] || { echo 'Retention must be at least one day' >&2; exit 1; }
export PGPASSWORD="$(cat "$PGPASSWORD_FILE")"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
file="/backups/istay-$stamp.dump"
tmp="$file.partial"
trap 'rm -f "$tmp"' EXIT INT TERM
pg_dump --format=custom --no-owner --no-acl --file="$tmp"
# A dump is promoted atomically only if pg_dump AND archive readability succeed.
pg_restore --list "$tmp" >/dev/null
mv "$tmp" "$file"
sha256sum "$file" > "$file.sha256"
date -u +%s > /backups/.last-success.tmp
mv /backups/.last-success.tmp /backups/.last-success
# Delete only this application's old, finalized backups after a successful new backup.
find /backups -maxdepth 1 -type f -name 'istay-*.dump' -mtime "+${RETENTION_DAYS:-30}" -exec rm -f {} \;
find /backups -maxdepth 1 -type f -name 'istay-*.dump.sha256' -mtime "+${RETENTION_DAYS:-30}" -exec rm -f {} \;
echo "Database backup completed: $(basename "$file")"

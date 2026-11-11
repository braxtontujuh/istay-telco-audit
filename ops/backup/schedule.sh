#!/bin/sh
set -eu
# Run immediately at startup, then once per UTC day at/after 19:00 (03:00 MYT).
# Polling retries failures every minute; a sleeping/offline PC catches up when Docker starts.
while :; do
  now="$(date -u +%s)"
  last="$(cat /backups/.last-success 2>/dev/null || echo 0)"
  # Latest scheduled UTC slot (19:00), including yesterday's slot before today's 19:00.
  slot="$(( now - (now % 86400) + 68400 ))"
  if [ "$now" -lt "$slot" ]; then slot="$((slot - 86400))"; fi
  if [ "$last" = 0 ] || [ "$last" -lt "$slot" ]; then
    if ! sh /opt/backup/backup.sh; then echo 'BACKUP FAILED; retrying in 60 seconds' >&2; fi
  fi
  sleep 60 &
  wait $!
done

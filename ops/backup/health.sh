#!/bin/sh
set -eu
last="$(cat /backups/.last-success)"
age="$(( $(date -u +%s) - last ))"
[ "$age" -ge 0 ] && [ "$age" -lt 93600 ]

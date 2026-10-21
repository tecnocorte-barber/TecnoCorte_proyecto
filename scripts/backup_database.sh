#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
log="backups/backup-script.log"
printf '%s START backup\n' "$timestamp" >> "$log"
python manage.py backup_database >> "$log" 2>&1
printf '%s END backup status=%s\n' "$(date -u +%Y%m%dT%H%M%SZ)" "$?" >> "$log"

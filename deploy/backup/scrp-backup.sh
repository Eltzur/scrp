#!/usr/bin/env bash
# SU11A-82 (SU11A-79 H3): the daily database backup, uploaded ENCRYPTED.
#
# Installed as /usr/local/bin/scrp-backup.sh (root:root 755), run by
# scrp-backup.service (04:00 Asia/Jerusalem, as root). It replaces the earlier
# script, which uploaded the same pg_dump in the clear to b2:<bucket>/daily/.
#
#   1. pg_dump -Fc of the database (as postgres, peer auth: no password here)
#      to LOCAL_DIR/<db>-YYYY-MM-DD.dump, written to a temp name and renamed
#      only when complete; checked with pg_restore --list.
#   2. Local rotation: 7 days; Sundays up to 28 days; the 1st of a month up to
#      180 days (unchanged from the earlier script).
#   3. rclone copy to ${REMOTE}${SUBDIR}/ - REMOTE must be an rclone CRYPT
#      remote (e.g. "b2crypt:", layered on b2:<bucket>/enc). The script refuses
#      a non-crypt remote unless ALLOW_PLAIN=1 (an emergency switch only).
#   4. A check that the object is listed on the remote with the same size.
#
# Settings: /etc/xxl/backup.conf (KEY=value, no secrets; example
# deploy/backup/backup.conf.example). The crypt passphrase and salt live only in
# root's rclone config (obscured) and in Dude's password manager - never here.
# Any failure exits non-zero -> scrp-backup.service fails -> OnFailure mail
# (deploy/systemd/dropins/scrp-backup.service.d/xxl-onfailure.conf).
set -euo pipefail

CONF="${XXL_BACKUP_CONF:-/etc/xxl/backup.conf}"
DB="xxl_super"
LOCAL_DIR="/var/backups/scrp"
LOG="${XXL_BACKUP_LOG:-/var/log/scrp-backup.log}"
REMOTE=""
SUBDIR="daily"
RCLONE_CONFIG="/root/.config/rclone/rclone.conf"
ALLOW_PLAIN="0"
KEEP_DAILY_DAYS=7
KEEP_SUNDAY_DAYS=28
KEEP_MONTHLY_DAYS=180

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG" ; }
die() { log "ERROR: $*"; exit 1; }

# keep_dump NAME TODAY  ->  exit 0 = keep, 1 = delete. Pure (tests call it).
# NAME is <db>-YYYY-MM-DD.dump; TODAY is YYYY-MM-DD. Unknown names are kept.
keep_dump() {
  local name="$1" today="$2" d age dow dom
  d="$(printf '%s' "$name" | sed -nE 's/^.*-([0-9]{4}-[0-9]{2}-[0-9]{2})\.dump$/\1/p')"
  [ -n "$d" ] || return 0
  age=$(( ( $(date -u -d "$today" +%s) - $(date -u -d "$d" +%s) ) / 86400 ))
  dow="$(date -u -d "$d" +%u)"   # 7 = Sunday
  dom="$(date -u -d "$d" +%d)"
  [ "$age" -lt "$KEEP_DAILY_DAYS" ] && return 0
  [ "$dow" = "7" ] && [ "$age" -lt "$KEEP_SUNDAY_DAYS" ] && return 0
  [ "$dom" = "01" ] && [ "$age" -lt "$KEEP_MONTHLY_DAYS" ] && return 0
  return 1
}

# remote_type NAME:  ->  the rclone type of that remote ("crypt", "b2", ...).
# `rclone listremotes --long` prints names and types only, never secrets.
remote_type() {
  rclone listremotes --long --config "$RCLONE_CONFIG" | awk -v r="$1" '$1 == r { print $2 }'
}

main() {
  [ -r "$CONF" ] && . "$CONF"
  [ -n "$REMOTE" ] || die "REMOTE is not set in $CONF (expected a crypt remote such as b2crypt:)"
  case "$REMOTE" in *:) ;; *) die "REMOTE must end with ':' (got '$REMOTE')";; esac

  local type
  type="$(remote_type "$REMOTE")"
  [ -n "$type" ] || die "rclone remote $REMOTE not found in $RCLONE_CONFIG"
  if [ "$type" != "crypt" ] && [ "$ALLOW_PLAIN" != "1" ]; then
    die "rclone remote $REMOTE is type '$type', not crypt: refusing to upload an unencrypted dump"
  fi

  local today dump tmp size remote_size
  today="$(date +%Y-%m-%d)"
  dump="$LOCAL_DIR/$DB-$today.dump"
  tmp="$dump.partial"
  install -d -o postgres -g postgres -m 750 "$LOCAL_DIR"

  log "pg_dump $DB -> $dump"
  rm -f "$tmp"
  runuser -u postgres -- pg_dump -Fc -d "$DB" -f "$tmp" || die "pg_dump failed"
  runuser -u postgres -- pg_restore --list "$tmp" > /dev/null || die "pg_restore --list cannot read the new dump"
  mv -f "$tmp" "$dump"
  chmod 640 "$dump"
  size="$(stat -c %s "$dump")"
  log "dump OK: $size bytes"

  log "upload -> ${REMOTE}${SUBDIR}/ (type $type)"
  rclone copy "$dump" "${REMOTE}${SUBDIR}/" --config "$RCLONE_CONFIG" --retries 3 --low-level-retries 10 \
    || die "rclone copy failed"
  remote_size="$(rclone lsl "${REMOTE}${SUBDIR}/" --config "$RCLONE_CONFIG" --include "$(basename "$dump")" \
                 | awk '{ print $1 }' | head -1)"
  [ "$remote_size" = "$size" ] || die "the uploaded object is missing or has a different size (local $size, remote '${remote_size:-none}')"
  log "upload OK: $(basename "$dump") on ${REMOTE}${SUBDIR}/"

  local f kept=0 removed=0
  for f in "$LOCAL_DIR"/"$DB"-*.dump; do
    [ -e "$f" ] || continue
    if keep_dump "$(basename "$f")" "$today"; then kept=$((kept + 1)); else rm -f "$f"; removed=$((removed + 1)); fi
  done
  log "local rotation: kept $kept, removed $removed"
  log "backup done"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  main "$@"
fi

#!/usr/bin/env bash
# Logical backup of the AarogyaOS database: custom-format pg_dump, encrypted, checksummed.
#
#   PGHOST=... PGUSER=... PGPASSWORD=... PGDATABASE=aarogya \
#   BACKUP_PASSPHRASE_FILE=/run/secrets/backup_passphrase BACKUP_DIR=/backups ./backup.sh
#
# A dump contains patient data, so this REFUSES to write an unencrypted file. The passphrase must
# be stored apart from the backups (secret manager), and so must AAROGYA_FIELD_ENCRYPTION_KEY:
# without that key the encrypted identifiers (ABHA numbers) inside a restored dump are unreadable.
# This is a logical backup (restore point = when it ran). Point-in-time recovery needs continuous WAL
# archiving or a managed-database equivalent; see docs/OPERATIONS.md.
set -euo pipefail

: "${PGDATABASE:?set PGDATABASE}"
: "${BACKUP_DIR:?set BACKUP_DIR}"
: "${BACKUP_PASSPHRASE_FILE:?set BACKUP_PASSPHRASE_FILE (encryption is mandatory)}"
[ -s "$BACKUP_PASSPHRASE_FILE" ] || { echo "passphrase file is empty or missing" >&2; exit 1; }

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"
umask 077
out="$BACKUP_DIR/aarogya-$stamp.dump.gpg"

pg_dump --format=custom --no-owner --no-privileges --compress=6 "$PGDATABASE" \
  | gpg --batch --yes --quiet --symmetric --cipher-algo AES256 \
        --passphrase-file "$BACKUP_PASSPHRASE_FILE" --output "$out"

( cd "$BACKUP_DIR" && sha256sum "$(basename "$out")" > "$(basename "$out").sha256" )
echo "backup written: $out"

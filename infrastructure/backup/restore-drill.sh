#!/usr/bin/env bash
# Proves a backup can be restored and that the safety properties survived the round trip.
# Restores into a scratch database, checks it, and drops it. Run this on a schedule (monthly at
# least) and after any change to backups: an untested backup is a hope, not a backup.
#
#   PGHOST=... PGUSER=<role that may CREATE DATABASE> PGPASSWORD=... \
#   BACKUP_PASSPHRASE_FILE=... ./restore-drill.sh /backups/aarogya-<stamp>.dump.gpg
#
# Exits non-zero (and says why) if the checksum, restore or any check fails.
set -euo pipefail

file="${1:?usage: restore-drill.sh BACKUP.dump.gpg}"
: "${BACKUP_PASSPHRASE_FILE:?set BACKUP_PASSPHRASE_FILE}"
scratch="aarogya_restore_drill_$$"
here="$(cd "$(dirname "$file")" && pwd)"
base="$(basename "$file")"

( cd "$here" && sha256sum --check --quiet "$base.sha256" ) || { echo "FAIL: checksum mismatch" >&2; exit 1; }

cleanup() { dropdb --if-exists "$scratch" >/dev/null 2>&1 || true; }
trap cleanup EXIT
createdb "$scratch"

gpg --batch --quiet --decrypt --passphrase-file "$BACKUP_PASSPHRASE_FILE" "$file" \
  | pg_restore --no-owner --no-privileges --exit-on-error --dbname "$scratch"

q() { psql -X -A -t -d "$scratch" -c "$1"; }
fail() { echo "FAIL: $1" >&2; exit 1; }

[ "$(q "select count(*) from alembic_version")" = "1" ] || fail "migration version missing"
echo "migration version: $(q "select version_num from alembic_version")"

# Every table that holds an organisation's data must still have FORCED row-level security.
unprotected="$(q "select string_agg(c.relname, ', ') from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public' and c.relkind = 'r'
    and exists (select 1 from information_schema.columns k
                where k.table_name = c.relname and k.column_name = 'organisation_id')
    and c.relname not in ('organisations')
    and not (c.relrowsecurity and c.relforcerowsecurity)")"
[ -z "$unprotected" ] || fail "row-level security not forced on: $unprotected"
echo "row-level security: forced on every tenant table"

# Immutability triggers must have come back with the data.
for t in audit_logs transcript_segments consents ai_candidates investigation_results; do
  n="$(q "select count(*) from pg_trigger where tgrelid = 'public.$t'::regclass and not tgisinternal")"
  [ "$n" -ge 1 ] || fail "no protective trigger on $t"
done
echo "immutability triggers: present"

echo "rows: audit_logs=$(q 'select count(*) from audit_logs') patients=$(q 'select count(*) from patients') encounters=$(q 'select count(*) from encounters')"
echo "RESTORE DRILL PASSED for $base"

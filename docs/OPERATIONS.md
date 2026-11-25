# Operations runbook

Everything here was exercised in a single-machine development environment only. Nothing has run in a
production-like cluster, behind a load balancer, on managed Postgres, or under a clinical load. Treat the
numbers as a baseline for comparing changes, and the procedures as tested building blocks.

## Health and readiness
- `GET /health`: process is up (liveness). Does not touch the database.
- `GET /ready`: database reachable **and** its migration revision equals this code's head. `503 migrations_pending`
  otherwise, so a rollout that was not migrated never receives traffic. Driver errors are never returned.

## Metrics (`GET /metrics`, Prometheus text)
- Disabled (404) in production until `AAROGYA_METRICS_TOKEN` is set; then needs `Authorization: Bearer <token>`.
  Without a token it is open in development only. Keep it on the internal network anyway.
- Series: `aarogya_http_requests_total{method,route,status}`, `aarogya_http_request_duration_seconds` (histogram),
  `aarogya_job_last_success_timestamp_seconds{job}`. Labels are **route templates** (`/patients/{patient_id}`):
  no identifiers, names, query strings or bodies reach a monitoring system. (The access log records the same route templates under `route`, not raw paths; keep logs in-region regardless.)
- Counters are per process; sum across workers/replicas.
- Suggested alerts (starting points, tune with real traffic): 5xx rate > 1% for 5 min; p95 latency above your
  agreed target; `/ready` failing; any job's last success older than twice its schedule; 401/403 spikes.
- Not built: distributed tracing (OpenTelemetry), log shipping, dashboards, AI cost dashboards. `/usage/speech` and
  `/usage/ai` expose metering; cost stays empty until real prices are configured.

## Scheduled jobs
Run `python -m app.cli run-job NAME` from cron or a Kubernetes CronJob using the API image. A database advisory lock
prevents overlap (the second run records `SKIPPED`); each run writes a PHI-free row in `job_runs`; failures record
only the exception class.

| Job | What it does | Suggested schedule |
|---|---|---|
| `purge-audio` | Deletes retained audio past its retention or after consent withdrawal (transcripts untouched) | hourly |
| `pause-stale-recordings` | Pauses recordings whose audio stopped, so none claims to be live | every minute |
| `purge-refresh-tokens` | Deletes refresh tokens 30+ days past expiry | daily |
| `purge-idempotency-keys` | Deletes request keys older than two days (they only guard against retries) | daily |

## Database
- The app connects as a **non-superuser** (row-level security is bypassed by superusers, and `/ready`-style checks
  cannot detect that; tests do). Migrations run as the same role in this repo; a stricter setup uses a separate
  owner role for DDL.
- **pgvector is optional.** If a DBA runs `CREATE EXTENSION vector` *before* migration 0006 (or re-applies the
  block in 0006 afterwards), reference search runs in the database with exact cosine distance; otherwise it ranks
  in Python. Results are the same (tested). Approved corpora are small; add an HNSW index per embedding model if one
  grows past tens of thousands of chunks. Changing embedding model means re-embedding documents.
- Connection pool size and `max_connections` have not been tuned; measure under real load.

## Backups and disaster recovery
Scripts: `infrastructure/backup/backup.sh` (encrypted, checksummed `pg_dump`; refuses to write plaintext) and
`infrastructure/backup/restore-drill.sh` (restores into a scratch database, verifies the checksum, migration
version, **forced row-level security on every tenant table** and **immutability triggers**, then drops it).
Both were run here against a database with data; a tampered backup was rejected.

What is NOT covered by these scripts and must be decided before go-live:
- **RPO / RTO targets.** A nightly logical dump gives an RPO of up to a day. Clinical use likely needs point-in-time
  recovery: continuous WAL archiving, or a managed Postgres in an Indian region with PITR. Set the targets with the
  clinical lead; they are not defined in this repo.
- **Keys.** Back up `AAROGYA_FIELD_ENCRYPTION_KEY` and the backup passphrase separately from the backups and from
  each other. Without the field key, encrypted identifiers (ABHA numbers) in a restored database are unreadable.
  Rotation exists (see "Rotating the field encryption key" below); keep retired keys as long as backups made under them may be restored. The same key also keys the prescription seal.
- **Audio.** Retained audio lives in the audio store, not the database, and is separately encrypted. The only store
  local-disk store must be backed up with its volume. The S3 store (`AAROGYA_AUDIO_STORE=s3`) relies on the bucket's
  versioning and replication; turn versioning on so a purge or a mistaken delete can be undone within the retention
  window you choose. With `s3`, a recording is spooled to `AAROGYA_AUDIO_STORE_PATH` while open and uploaded when its
  connection closes; an upload that fails stays there and is retried by the `purge-audio` job. Losing that volume
  before the retry loses those recordings' audio, never their transcripts. Restore has been tested against an
  in-memory S3 only. Or leave audio retention off (the default).
- **Retention of backups** must respect the patient's erasure/withdrawal rights and legal retention rules: not decided.
- Run the restore drill on a schedule (monthly at least) and after any backup change; alert if it fails.

## One live instance, or several with Redis

Without Redis, live transcript state is in process memory, so the API holds a PostgreSQL advisory lock for as long as it runs (`app/core/instance.py`, on by default in production). A second worker or a second container cannot take the lock: its `/ready` returns 503 `{"status":"standby"}` and it refuses audio connections with close code 4503. If you see `standby` on the only instance you meant to run, another process is still alive.

Two consequences. Deployments are stop-then-start: a rolling update that waits for the new instance to be ready will not finish, because the new instance cannot be ready while the old one holds the lock. And any restart interrupts recordings in progress: on start-up they are marked paused with reason `SERVER_RESTART`, saved transcript lines are kept, and the clinician chooses whether to resume. Deploy outside clinic hours.

With `AAROGYA_REDIS_URL` set, the live partial line and the one-connection-per-session claim are kept in Redis (`app/speech/live.py`), so several workers and containers may serve recordings and the instance lock is off by default (`AAROGYA_SINGLE_INSTANCE_GUARD` still forces it on). A process renews the claim for each connection it serves every five seconds; if it dies, the claim lapses within 15 seconds and the app can reconnect to any instance. An instance starting up pauses only recordings that no running instance holds, so a rolling deployment no longer interrupts recordings on the instances that stay up. A WebSocket served by an instance that is stopped is still cut, and that recording pauses until the clinician resumes it. If Redis cannot be reached, partial lines are not shown, duplicate connections are still refused on the same process, and start-up pauses nothing it cannot confirm is orphaned (the stale-recording job pauses those once their audio stops). This has been tested with several API instances in one test process sharing a real Redis, not yet on a hosting platform.

## Usage allowances

An administrator can set a monthly cap on speech minutes and on AI requests (Organisation settings in the app, or the policy endpoint). `GET /api/v1/usage/limits` returns this month's use against each cap with a state of `UNLIMITED`, `OK`, `NEAR` (past the alert share, 80 percent by default) or `REACHED`. Reaching a cap refuses new recordings or model calls with code `usage_limit_reached`; a recording already running is not cut off and manual work is never blocked. Months are calendar months in UTC. There is no outbound alert yet: someone has to look at the usage screen, or a monitor has to poll the endpoint.

## Known scaling limits (read before running more than one container)
1. **Without Redis, live (partial) transcripts and the duplicate-connection guard are held in process memory**, and
   the instance lock allows one process to serve recordings. Set `AAROGYA_REDIS_URL` before running more than one
   (see above). Finalised transcript segments are always in the database, so a lost partial only loses the
   unfinalised words.
2. The per-minute AI limit counts database rows, so it is correct across processes either way.
3. Login and patient-search rate limits are per process unless `AAROGYA_REDIS_URL` is set (see `16-SECURITY.md`), on
   top of per-account lockout.

## Load test (what exists, what it showed)
`services/api/scripts/loadtest.py` runs mixed clinic traffic (search, chart, clinical state, vitals, notes) from N
concurrent users. Run once here: 10 users, 20 s, 2 uvicorn workers, Postgres and load generator on the same 4-core
sandbox: **~147 requests/s, zero errors, p50 52-78 ms, p95 84-133 ms, p99 136-311 ms** per operation. This says only
that the code has no gross bottleneck at that scale on that machine. It excludes login (Argon2), AI, audio streaming
and the mobile network. A real capacity test needs a production-like stack and a realistic mix.

## Dependency scanning
CI runs `pip-audit` and `npm audit` (advisory, non-blocking until triaged). Locally: pip-audit found nothing. `npm
audit --omit=dev` reports 43 findings (27 high), all transitive build/test tooling (Metro, Jest, Expo CLI,
`node-forge` via Expo's signing tooling, `braces`/`micromatch`); none is code shipped inside the app bundle. They
are cleared by upgrading Expo SDK; track that.

## Not done
Container image build and registry (no Docker in the build environment, so the Dockerfile/compose changes are
untested), Kubernetes/Terraform manifests, TLS and WAF, secret manager integration, managed-Postgres setup, S3 audio
store, Redis, OpenTelemetry, log shipping, SLOs, an on-call process, penetration test, DPDP/regulatory review, clinical
safety sign-off, and any real LLM/speech/translation/terminology/drug-knowledge provider.

## Rotating the field encryption key

Rotation changes the key that protects patient identifiers (and keys their blind index). Do it on a schedule, and at once if the key may have leaked. Take a backup first.

1. Generate a new key: `python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"`.
2. Set `AAROGYA_FIELD_ENCRYPTION_KEY` to the new key and `AAROGYA_FIELD_ENCRYPTION_PREVIOUS_KEYS` to the old one, then restart. New data uses the new key; old data still reads; searches for identifiers check both.
3. Run `python -m app.cli rotate-field-key`. It re-encrypts every identifier and rebuilds its index, then re-encrypts retained audio from recordings that have ended. Each audio file is rewritten beside the original and swapped in whole, so an interrupted run leaves one complete copy; the command can be run again. Recordings that are active or paused are left alone, because they may still be written to: the command lists how many and exits with status 1.
4. Once the command exits with status 0, nothing needs the old key any more, so remove it from `AAROGYA_FIELD_ENCRYPTION_PREVIOUS_KEYS`. Keep an offline copy of retired keys for as long as backups made under them may need restoring.

Tested on a development database only (`tests/test_key_rotation.py`); rehearse on a restore of production data before relying on it.

## Migration 0017: one active visit per patient

0017 adds a unique index allowing each patient only one visit that is waiting, checked in or in consultation. The application already refused a second check-in; the index makes that hold when two requests arrive together. If the upgrade fails on this index, a patient already has two active visits from before: find them with

```sql
select patient_id, count(*) from appointments
where status in ('WAITING', 'CHECKED_IN', 'IN_CONSULTATION')
group by patient_id having count(*) > 1;
```

close or cancel the extra visit through the app, and run the upgrade again. 0016 and 0017 are reversible (`alembic downgrade 0015`); `tests/test_migrations.py` checks this with data in place.


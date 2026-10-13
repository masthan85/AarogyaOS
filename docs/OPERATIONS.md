# Operations runbook (Phase 7)

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
  no identifiers, names, query strings or bodies reach a monitoring system. (The access log does record the raw
  path, which contains record ids; treat logs as sensitive and keep them in-region.)
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
  each other. Without the field key, encrypted identifiers (ABHA numbers) in a restored database are unreadable;
  there is no key rotation yet.
- **Audio.** Retained audio lives in the audio store, not the database, and is separately encrypted. The only store
  built is a local-disk one; an S3-compatible encrypted store (with KMS) is not built. Back it up, or leave audio
  retention off (the default).
- **Retention of backups** must respect the patient's erasure/withdrawal rights and legal retention rules: not decided.
- Run the restore drill on a schedule (monthly at least) and after any backup change; alert if it fails.

## Known scaling limits (read before running more than one container)
1. **Audio streaming and live (partial) transcripts are held in process memory.** Run one worker per container and
   keep a session's WebSocket and its transcript polling on the same container (sticky routing). Finalised transcript
   segments are in the database, so a lost partial only loses the unfinalised words. A Redis-backed hub is the fix and
   is not built.
2. The audio gateway's duplicate-connection guard and the per-minute AI rate limit are per-process too (the AI limit
   counts database rows, so it is correct across replicas).
3. No rate limiting on login beyond per-account lockout. Put a WAF / rate limiter in front.

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

## Not done in Phase 7
Container image build and registry (no Docker in the build environment, so the Dockerfile/compose changes are
untested), Kubernetes/Terraform manifests, TLS and WAF, secret manager integration, managed-Postgres setup, S3 audio
store, Redis, OpenTelemetry, log shipping, SLOs, an on-call process, penetration test, DPDP/regulatory review, clinical
safety sign-off, and any real LLM/speech/translation/terminology/drug-knowledge provider.

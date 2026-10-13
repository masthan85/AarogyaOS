# Deployment

**Not production-ready.** `OPERATIONS.md` lists what is built, what was tested, and what is missing.

## Release steps (one release, in order)
1. Build the API image (`services/api/Dockerfile`; non-root, no migration on start).
2. Run migrations **once**: `python -m alembic upgrade head && python -m app.cli seed` (the compose file has a
   one-shot `migrate` service; on Kubernetes use a Job or a pre-upgrade hook).
3. Roll out the API. `/ready` returns 503 until the schema matches, so traffic waits.
4. Schedule the jobs (OPERATIONS.md).

## Required configuration (production refuses to start without it)
`AAROGYA_ENVIRONMENT=production`; `AAROGYA_JWT_SECRET` (32+ random chars); `AAROGYA_FIELD_ENCRYPTION_KEY`
(base64 of 32 random bytes; back it up); `AAROGYA_DATABASE_URL` with a non-development password and a
**non-superuser** role; explicit `AAROGYA_CORS_ORIGINS` (never `*`). Providers are never defaulted in production:
choose `AAROGYA_SPEECH_PROVIDER` / `AAROGYA_LLM_PROVIDER` / `AAROGYA_EMBEDDING_PROVIDER` deliberately (the
development providers are refused). No real adapters exist yet. Set `AAROGYA_METRICS_TOKEN` to enable `/metrics`.

## In front of the API
Terminate TLS (the API sets HSTS in production and `Cache-Control: no-store` on `/api/`), add a WAF and rate
limits, route WebSocket audio with sticky sessions, and keep `/metrics` internal. Request bodies over
`AAROGYA_MAX_REQUEST_BYTES` (5 MB) are refused.

## Before real patients
Data residency in India confirmed for every component, including any AI vendor; data-processing agreements;
the regulatory and legal reviews in `SECURITY.md` and `CLINICAL_SAFETY.md` (DPDP, CDSCO SaMD status, clinical
safety officer); penetration test; restore drill passed in the target environment.

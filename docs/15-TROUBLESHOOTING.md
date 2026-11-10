# Troubleshooting

Entries marked "reproduced" were hit while validating this documentation; the rest come from reading the code and the operations notes. Start with the logs: the API writes JSON lines with a `correlation_id`, and every response carries `X-Request-ID`.

## Starting the API

**`ValueError: Field encryption key must decode to exactly 32 bytes`** (reproduced). The `.env` file or environment contains `AAROGYA_FIELD_ENCRYPTION_KEY=` with no value (older copies of `.env.example` did this). A variable that is present but empty overrides the development default. Generate a key (`python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"`) or delete the line.

**The API ignores my `.env`** (reproduced). The file is read from the directory you start the API in. Start it from `services/api` and keep the file at `services/api/.env`. A `.env` in the repository root is read only by Docker Compose when you pass it with `--env-file`.

**`connection refused` or `fe_sendauth: no password supplied`.** PostgreSQL is not running on the host and port in `AAROGYA_DATABASE_URL`, or it asks for a password the URL does not supply. Check with `pg_isready`. If two PostgreSQL servers are installed, make sure the one you started is the one on port 5432.

**`/ready` returns 503 with `migrations_pending`.** The database is behind the code. Run `alembic upgrade head` and then `python -m app.cli seed` from `services/api`. `/ready` returning `unavailable` means the database cannot be reached at all.

**Right after an upgrade, some users get 403.** New permissions are added in code and copied into the database by `python -m app.cli seed`. Run it after every migration.

**`alembic: command not found` or "No config file".** Activate the virtual environment and run Alembic from `services/api`, where `alembic.ini` lives.

**Production start is refused.** The messages say what is wrong: a default or short JWT secret, the development field key, the development database password, a wildcard CORS origin, or a non-TLS Sarvam URL. A development speech, language-model or embedding provider is refused too; choose real ones. See `06-CONFIGURATION.md`.

**Tenant isolation looks switched off: one organisation can see another's rows.** The application is connected as a PostgreSQL superuser or a role with `BYPASSRLS`. Connect as an ordinary role (`NOSUPERUSER NOBYPASSRLS`).

## Running tests

**Every test errors with a connection failure.** `AAROGYA_TEST_ADMIN_URL` must point to a running PostgreSQL superuser. If the database stopped mid-run you will see `OperationalError` on every following test; restart it and rerun.

**A new table's tests see leftover rows.** Add the table to `TENANT_TABLES` in `tests/conftest.py`.

**The mobile contract test fails (`API contract`), or the backend `test_contract` test fails.** A response field changed. If the app's zod schema requires a field the API no longer returns, fix the schema or the API. If you changed an API response on purpose, regenerate the field list with `cd services/api && PYTHONPATH=. python scripts/export_contract.py` and commit `apps/mobile/src/api/contract.json`.

**Mobile tests fail after changing an API shape.** Update the zod schema in `apps/mobile/src/api/schemas.ts` and the fixtures that build typed objects, such as the invoice in `print.test.ts`.

## Using the app

**Expo Go says "Project is incompatible with this version of Expo Go".** The SDK of the project and of Expo Go differ. iPhones can only run the latest Expo Go, so the project follows the latest SDK (58 at the time of writing). When a newer SDK appears, upgrade the project (`npm install expo@<new>`, set the other packages to the versions in `node_modules/expo/bundledNativeModules.json`, then type-check, test and export) before updating Expo Go. On Android you can install an older Expo Go from expo.dev/go.

**The app cannot reach the API.** Check `EXPO_PUBLIC_API_URL`. An Android emulator reaches the host at `10.0.2.2`; a physical phone needs the computer's network address and port 8000 open in its firewall. The variable is baked in when the bundle starts, so restart Expo after changing it.

**The microphone plays a scripted conversation instead of my voice.** That is intended in development builds. Set `EXPO_PUBLIC_USE_MICROPHONE=1` in a development or release build; Expo Go cannot do it. This path has not run on a device, so follow `DEVICE_TEST_PLAN.md`.

**Recording will not start: 409 `consent_required`.** The response lists the missing purposes. Capture them for that patient (reception or nurse) and try again. Consent withdrawn mid-recording ends the stream by design.

**The Draft EMR tab is empty or says analysis failed.** AI endpoints report an unavailable model as a normal response with status `FAILED`. Check that AI is switched on for the organisation (Administration, policy), that the patient gave AI-processing consent, and which `AAROGYA_LLM_PROVIDER` is set. With the development provider the "findings" are naive keyword matches. Every screen still works by hand.

**Hindi appears in Roman letters.** A fixed language hint can cause this. Leave `AAROGYA_SARVAM_USE_LANGUAGE_HINT` false, or try `AAROGYA_SARVAM_MODE=codemix`.

**429 responses.** The login or patient-search limit was reached (60 a minute by default). Behind a proxy that hides client addresses all users share one login bucket; configure the proxy to pass the real address.

**An account is locked.** Five failed logins lock an account for 15 minutes (`AAROGYA_MAX_FAILED_LOGINS`, `AAROGYA_LOCKOUT_MINUTES`). Wrong two-step codes count as failed logins.

**Sign-in asks for a code and the phone is lost.** Use one of the eight recovery codes (each works once). If those are gone too, an administrator with `user:manage` can clear the second factor with `POST /users/{id}/mfa/reset`; the person then signs in with the password alone and can set it up again. A code that was just used is refused for the rest of its 30 seconds, so wait for the next one. Codes depend on the phone's clock being right.

**A signed prescription's check says "cannot be checked" or "does not match".** "Cannot be checked" means it was signed before seals existed (migration 0014). "Does not match" means the stored prescription differs from what was signed, or the field encryption key changed without the old one in `AAROGYA_FIELD_ENCRYPTION_PREVIOUS_KEYS`. Restore the old key to the list before treating it as tampering.

**An invoice cannot be voided.** Money or a credit note is recorded on it. Issue a full credit note and refund what was paid.

**Retained audio is not being deleted.** The `purge-audio` job is not scheduled (the repository ships no scheduler), or the patient is under a legal hold. Check `job_runs` and the patient's holds.

## Docker

**`required variable ... is missing a value`.** Pass the env file: `--env-file infrastructure/dev.env`. The compose file requires the database passwords, the JWT secret and the field key.

**The API container keeps restarting.** Read its logs. The common causes are the migration service failing, or a production-mode validation message if `AAROGYA_ENVIRONMENT` was set to production with development values.

**Rebuild from scratch.** `docker compose --env-file infrastructure/dev.env -f infrastructure/docker-compose.yml down -v` removes the database and audio volumes. The Docker route has not been run in the authoring environment, so please report the first thing that fails.

## Database

**pgvector extension errors in migration 0006.** The extension is optional. Without it the migration skips the vector column and search ranks in Python, with the same results. To enable it, run `CREATE EXTENSION vector` as a superuser before migrating (or re-run the block in 0006 afterwards).

**Appointments overlap errors.** The database refuses overlapping scheduled appointments for one practitioner (an exclusion constraint that needs `btree_gist`). Choose another slot.

## Still stuck

Search `docs/OPERATIONS.md` for runbook procedures (restore drill, key rotation, job freshness) and `docs/CLINICAL_SAFETY.md` if the behaviour in question is a safety control that is working as intended.

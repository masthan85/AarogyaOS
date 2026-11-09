# Configuration

All backend settings are defined once, in `services/api/app/core/config.py`, as environment variables with the prefix `AAROGYA_`. The API also reads a `.env` file from the directory it is started in (for the standard setup, `services/api/.env`). The table below was generated from that file, so it matches the code; `.env.example` in the repository root is a starting template that shows the most common settings but not all of them.

Two behaviours are worth knowing before you start. If a variable is absent, its default applies. If it is present but empty, the empty value applies. That matters for `AAROGYA_FIELD_ENCRYPTION_KEY`: with no variable at all, development uses a built-in key, but an explicitly empty value makes the API refuse to start. The example file now keeps both secrets commented out for that reason. Second, `AAROGYA_ENVIRONMENT=production` switches on strict validation (see "Production rules").

## Core and security

| Variable | Default | Meaning |
|---|---|---|
| `AAROGYA_ENVIRONMENT` | `development` | `development`, `test` or `production`. Production changes validation, disables `/docs`, enables HSTS and refuses development providers |
| `AAROGYA_DATABASE_URL` | `postgresql+psycopg://aarogya_app:aarogya_app@localhost:5432/aarogya` | SQLAlchemy URL. Must connect as a non-superuser role |
| `AAROGYA_JWT_SECRET` | development constant | Signs access tokens. At least 32 random characters in production |
| `AAROGYA_JWT_ALGORITHM` | `HS256` | Token signing algorithm |
| `AAROGYA_FIELD_ENCRYPTION_KEY` | development constant | Base64 of 32 random bytes. Encrypts patient identifiers, keys their lookup index, and, unless `AAROGYA_SEAL_KEYS` is set, keys the prescription seal. Back it up |
| `AAROGYA_FIELD_ENCRYPTION_PREVIOUS_KEYS` | empty | Comma-separated older keys, kept while data is re-encrypted after rotation and while old prescription seals must stay verifiable |
| `AAROGYA_SEAL_KEYS` | empty | Optional dedicated keys for the prescription seal: base64 of 32 random bytes each, comma separated. The first signs new seals; all are accepted when checking, together with keys derived from the field encryption key, so existing seals keep verifying. Set it before rotating the field key if you want seals to survive the rotation |
| `AAROGYA_ACCESS_TOKEN_MINUTES` | 15 | Access token lifetime, 1 to 60 |
| `AAROGYA_REFRESH_TOKEN_DAYS` | 14 | Refresh token lifetime, 1 to 90 |
| `AAROGYA_MAX_FAILED_LOGINS` | 5 | Failed attempts before an account locks (minimum 3) |
| `AAROGYA_LOCKOUT_MINUTES` | 15 | Lock duration |
| `AAROGYA_CORS_ORIGINS` | `[]` | JSON list of allowed origins. A wildcard is refused in production |
| `AAROGYA_LOGIN_ATTEMPTS_PER_MINUTE_PER_IP` | 60 | Per worker process; 0 turns the limit off |
| `AAROGYA_PATIENT_SEARCHES_PER_MINUTE_PER_USER` | 60 | Per worker process; 0 turns the limit off |
| `AAROGYA_MAX_REQUEST_BYTES` | 5000000 | Request body cap, 10 000 to 50 000 000 |
| `AAROGYA_LOG_LEVEL` | `INFO` | Python log level |
| `AAROGYA_METRICS_TOKEN` | empty | Bearer token for `/metrics`. Empty: open in development, disabled (404) in production |

## Speech

| Variable | Default | Meaning |
|---|---|---|
| `AAROGYA_SPEECH_PROVIDER` | empty (becomes `development` outside production) | `sarvam` or `development`. Production must choose explicitly |
| `AAROGYA_SPEECH_FALLBACK_PROVIDER` | empty | Provider to try if the first is unavailable |
| `AAROGYA_SARVAM_API_KEY` | empty | Registers the Sarvam provider. Also used for Sarvam translation, text-to-speech and chat |
| `AAROGYA_SARVAM_MODEL` | `saaras:v4` | Speech-to-text model |
| `AAROGYA_SARVAM_MODE` | `transcribe` | `transcribe`, `verbatim`, `translit` or `codemix` |
| `AAROGYA_SARVAM_USE_LANGUAGE_HINT` | false | Send the patient's language as a hint. Off because auto-detect did better in a live test |
| `AAROGYA_SARVAM_URL` | `wss://api.sarvam.ai/speech-to-text/ws` | Must be `wss://` in production |
| `AAROGYA_SARVAM_REST_URL` | `https://api.sarvam.ai` | Must be `https://` in production |
| `AAROGYA_SPEECH_MONITOR_INTERVAL_SECONDS` | 2 | How often the gateway re-checks consent and session state |
| `AAROGYA_SPEECH_MAX_SESSION_SECONDS` | 3600 | Hard limit on one recording, 60 to 14 400 |
| `AAROGYA_AUDIO_STORE_PATH` | `/tmp/aarogya-audio` | Local encrypted audio store. Development only; production needs an object store that is not built |

## Language model, translation and read-aloud

| Variable | Default | Meaning |
|---|---|---|
| `AAROGYA_LLM_PROVIDER` | empty (becomes `development` outside production) | `sarvam`, `anthropic`, `self_hosted` or `development` |
| `AAROGYA_ANTHROPIC_API_KEY` | empty | Registers the Anthropic provider |
| `AAROGYA_ANTHROPIC_MODEL` | `claude-opus-5-5` | Model identifier sent to the API |
| `AAROGYA_SARVAM_LLM_MODEL` | `sarvam-105b` | Model used when the provider is `sarvam` |
| `AAROGYA_SELF_HOSTED_LLM_URL` | empty | OpenAI-compatible server (vLLM, Ollama). Checked at startup; a model name is then required |
| `AAROGYA_SELF_HOSTED_LLM_MODEL` | empty | Model name on that server |
| `AAROGYA_SELF_HOSTED_LLM_API_KEY` | empty | Optional key for that server |
| `AAROGYA_SELF_HOSTED_LLM_JSON_MODE` | false | Set true only if the server supports `response_format: json_object` |
| `AAROGYA_EMBEDDING_PROVIDER` | empty (becomes `development` outside production) | Embeddings for reference search; only a development stand-in exists |
| `AAROGYA_LLM_TIMEOUT_SECONDS` | 60 | Per model call, up to 120 |
| `AAROGYA_AI_ANALYSES_PER_MINUTE` | 6 | Analysis runs per user; counted from database rows so correct across replicas |
| `AAROGYA_TRANSLATION_PROVIDER` | empty | `sarvam` or off |
| `AAROGYA_TTS_PROVIDER` | empty | `sarvam` or off |

Per-organisation switches (recording, AI, suggestions, audio retention, enabled languages, guardian age) are stored in the organisation's settings and edited in the app under Administration; they sit on top of these process-level settings.

## Production rules

With `AAROGYA_ENVIRONMENT=production` the API refuses to start unless: the JWT secret is not the development constant and is at least 32 characters; the field encryption key is not the development constant; the database URL does not use the development password; CORS origins do not include `*`; the Sarvam URLs use TLS. In addition, the development speech, language-model and embedding providers are refused, so a real provider must be chosen deliberately. `/docs` is disabled, HSTS is sent, and `/metrics` is disabled until a token is set.

## Docker Compose variables

These are read by `infrastructure/docker-compose.yml`, not by the API directly: `POSTGRES_SUPERUSER_PASSWORD` and `AAROGYA_APP_DB_PASSWORD` (the second becomes the password of the `aarogya_app` role created by `infrastructure/postgres/init-app-role.sh`), plus pass-through of the `AAROGYA_*` values for the secrets and providers listed above. Compose also accepts `SARVAM_API_KEY` as an alias for `AAROGYA_SARVAM_API_KEY`. `infrastructure/dev.env` contains development-only values.

## Variables read by helper scripts

The scripts in `services/api/scripts` that call Sarvam (`sarvam_hello.py`, `sarvam_services_check.py`, `extraction_live_check.py`) read the key from an unprefixed `SARVAM_API_KEY` in the environment or in a `.env` at the repository root. `scripts/smoke_recording.py` and `loadtest.py` take a server URL as an argument and need `AAROGYA_DATABASE_URL` for seeding.

## Test configuration

`AAROGYA_TEST_ADMIN_URL` (default `postgresql+psycopg://postgres@localhost:5432/postgres`) must point at a PostgreSQL superuser. The test suite uses it to create an isolated `aarogya_test` database and a non-superuser role that the application connects as.

## Mobile app

| Variable | Meaning |
|---|---|
| `EXPO_PUBLIC_API_URL` | Base URL of the API. `http://10.0.2.2:8000` reaches the host from an Android emulator |
| `EXPO_PUBLIC_USE_MICROPHONE` | `1` uses the real microphone in a development or release build. Never run on a device yet |
| `EXPO_PUBLIC_SIMULATED_AUDIO` | `1` forces the scripted sample conversation in non-development builds |

Everything named `EXPO_PUBLIC_*` is compiled into the app and visible to anyone who has it. App identity (bundle and package id `in.aarogyaos.app`, scheme `aarogyaos`) is in `apps/mobile/app.json`.

## Secrets handling

Never commit real values. `.env` is ignored by git at every level. Generate secrets locally with the commands in `05-INSTALLATION-SETUP.md`, keep the field encryption key in a secret manager with an offline copy, and keep vendor keys out of the mobile app entirely: it never holds them.

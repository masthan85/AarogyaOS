# Installation and setup

This guide gets the API and the mobile app running on a development machine. Every command in the "Local setup" sections was run against this repository on a clean database; the Docker route could not be run, because the build environment has no Docker daemon, and is marked as such. Production deployment is a separate document: `11-DEPLOYMENT-GUIDE.md`.

## What you need

| Software | Version | Notes |
|---|---|---|
| Python | 3.12 or newer | CI uses 3.12; the setup below was also run on 3.13 |
| PostgreSQL | 16 | pgvector is optional. Without it, reference search ranks in Python with the same results |
| Node.js and npm | Node 22 | CI uses 22; npm 10 was used for the checks below |
| Docker Desktop | current | Only for the Docker route |
| Android emulator or phone, Expo tooling | | Only to run the mobile app; the web build is not a supported target |

You do not need any third-party account to run the product. Speech and language-model providers default to synthetic development stand-ins outside production.

## Local setup: API

All commands run from `services/api`.

1. Create a virtual environment and install the package with its development tools:

   ```bash
   python -m venv .venv
   . .venv/bin/activate
   pip install -e ".[dev]"
   ```

2. Create the database and a role for the application. The role must not be a superuser, because PostgreSQL superusers bypass row-level security and that would silently switch off tenant isolation. As a PostgreSQL superuser:

   ```sql
   CREATE ROLE aarogya_app LOGIN PASSWORD 'choose-a-password' NOSUPERUSER NOCREATEROLE NOBYPASSRLS;
   CREATE DATABASE aarogya OWNER aarogya_app;
   ```

3. Configure the application. Settings come from environment variables with the prefix `AAROGYA_`, and from a file named `.env` in the directory you run the API from. Run from `services/api` means the file is `services/api/.env`. A `.env` in the repository root is not read by the API; it is only used by Docker Compose.

   ```bash
   cp ../../.env.example .env
   ```

   Then edit `.env`. At minimum set `AAROGYA_DATABASE_URL` to match the role you created, for example `postgresql+psycopg://aarogya_app:choose-a-password@localhost:5432/aarogya`. The JWT secret and the field encryption key are commented out in the example, which makes development use built-in values that protect nothing. For anything beyond a throwaway machine, uncomment and set your own:

   - `AAROGYA_JWT_SECRET`: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
   - `AAROGYA_FIELD_ENCRYPTION_KEY`: `python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"`. Keep a copy; losing it makes stored identifiers unreadable.

   Do not leave either variable present but empty: an empty field encryption key stops the API from starting. Production refuses the built-in values. All other settings have working development defaults; `06-CONFIGURATION.md` lists them.

4. Create the schema and the reference data (roles and permissions). This is the same pair of commands every release must run:

   ```bash
   alembic upgrade head
   python -m app.cli seed
   ```

5. Create demo data, optionally. This makes a demo organisation, users for every role and one patient, using invented names and a published password, so only use it on a development database:

   ```bash
   python -m app.cli demo-seed
   ```

   It prints the sign-in details: organisation `demo-clinic`, password `Demo-pass-2026!`, and the users `admin`, `doctor`, `nurse`, `reception`, `pharmacist`, `lab` and `billing` at `@demo.example.com`. Running it again changes nothing. The command prints a lot of request log lines before the summary; that is expected.

   For a real installation, create the platform administrator instead and use that account to create organisations:

   ```bash
   python -m app.cli create-platform-admin
   ```

6. Start the API:

   ```bash
   uvicorn app.main:create_app --factory --reload
   ```

7. Check it. The API listens on port 8000 by default.

   ```bash
   curl localhost:8000/health        # {"status":"ok"}
   curl localhost:8000/ready         # {"status":"ready","migrations":"ok"}
   curl -X POST localhost:8000/api/v1/auth/login -H 'content-type: application/json' \
     -d '{"organisation_slug":"demo-clinic","email":"doctor@demo.example.com","password":"Demo-pass-2026!"}'
   ```

   The interactive API reference is at `http://localhost:8000/docs` (disabled in production).

## Local setup: mobile app

From `apps/mobile`:

```bash
npm install
EXPO_PUBLIC_API_URL=http://10.0.2.2:8000 npx expo start
```

`10.0.2.2` is how an Android emulator reaches the host machine. For a physical phone use the computer's address on the local network, for example `http://192.168.1.20:8000`, and allow port 8000 through the computer's firewall. Anything named `EXPO_PUBLIC_*` is compiled into the app, so never put a secret there.

In development builds the microphone is simulated: it plays a scripted sample conversation, not your voice. Set `EXPO_PUBLIC_USE_MICROPHONE=1` in a development or release build (not Expo Go) to use the real microphone; that path is unit-tested but has never run on a device, so follow `DEVICE_TEST_PLAN.md` first. `EXPO_PUBLIC_SIMULATED_AUDIO=1` forces the simulation in other builds.

To check the app compiles and tests pass without a device:

```bash
npm run typecheck
npm test
CI=1 npx expo export --platform android --output-dir /tmp/export   # produces an Android bundle
```

When adding Expo packages, use `npx expo install <package>` where the compatibility service is reachable; otherwise pin `expo-*` packages to `~57.0.0`.

## Walking through a visit

With the demo data loaded and the app pointing at the API: sign in as reception, find "Demo Patient", check in, and record consent for recording and AI processing. Sign in as the nurse for triage. Sign in as the doctor, open the consultation, switch AI assistance on in the Conversation tab, press Start and then Stop. The Draft EMR tab opens with what the built-in test extractor found. Billing staff then see the finished visit in "To bill".

## Optional providers

Nothing external is contacted unless you set it up. To use Sarvam speech-to-text and a real language model, add to `.env`:

```
AAROGYA_SARVAM_API_KEY=<your key>
AAROGYA_SPEECH_PROVIDER=sarvam
AAROGYA_LLM_PROVIDER=sarvam
```

Translation and read-aloud are separate switches (`AAROGYA_TRANSLATION_PROVIDER=sarvam`, `AAROGYA_TTS_PROVIDER=sarvam`). Anthropic needs `AAROGYA_ANTHROPIC_API_KEY` and `AAROGYA_LLM_PROVIDER=anthropic`; a self-hosted OpenAI-compatible server needs `AAROGYA_SELF_HOSTED_LLM_URL` and `AAROGYA_SELF_HOSTED_LLM_MODEL`. These providers send audio or text to a third party, so use invented content only until the data agreements in `16-SECURITY.md` are in place. The live check scripts in `services/api/scripts` are described in `SARVAM.md` and `DEVICE_TEST_PLAN.md`.

## Docker route (not validated here)

The compose file starts PostgreSQL (the pgvector image), a one-shot migration service and the API. It could not be run in the environment used to write this guide, so the compose file, the seed command and the migrations were checked separately; report the first thing that does not work.

1. Start Docker Desktop. From the repository folder run:

   ```bash
   docker compose --env-file infrastructure/dev.env -f infrastructure/docker-compose.yml up --build
   ```

   The first run builds the image. It is ready when `http://localhost:8000/health` returns `{"status":"ok"}`.

2. In a second terminal, create the demo organisation:

   ```bash
   docker compose --env-file infrastructure/dev.env -f infrastructure/docker-compose.yml exec api python -m app.cli demo-seed
   ```

3. Point the mobile app at `http://10.0.2.2:8000` (emulator) or the computer's network address (phone), as above.

`infrastructure/dev.env` holds development-only values that protect nothing. To add a provider key, create `infrastructure/dev.local.env` (ignored by git) with a copy of `dev.env` plus your keys and pass that file in place of `dev.env`. To stop, press Ctrl+C; to wipe the data, run the same command with `down -v` instead of `up --build`.

## Running the checks

Backend checks and tests are described in `10-TESTING-GUIDE.md`. In short, `ruff check .`, `ruff format --check .`, `mypy app` and `pytest -q` from `services/api`, with `AAROGYA_TEST_ADMIN_URL` pointing at a PostgreSQL superuser. If something does not work, see `15-TROUBLESHOOTING.md`.

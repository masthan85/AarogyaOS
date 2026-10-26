# Development

## Backend (`services/api`)
```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp ../../.env.example ../../.env      # fill secrets; use a NON-superuser DB role
alembic upgrade head && python -m app.cli seed
python -m app.cli create-platform-admin
uvicorn app.main:create_app --factory --reload
```
OpenAPI docs at `/docs` (non-production). Checks: `ruff check . && ruff format --check . && mypy app && pytest`.

Tests need a Postgres **superuser** URL in `AAROGYA_TEST_ADMIN_URL`
(default `postgresql+psycopg://postgres@localhost:5432/postgres`). The suite creates an isolated
`aarogya_test` database and a non-superuser role, because superusers bypass row-level security
and would make the tenant-isolation tests meaningless.

## Mobile (`apps/mobile`)
```bash
npm install
EXPO_PUBLIC_API_URL=http://10.0.2.2:8000 npx expo start
npm run typecheck && npm test
```
Use `npx expo install <pkg>` for new Expo packages where the Expo compatibility service is
reachable; otherwise pin to `~57.0.0` for `expo-*` packages.

## Try it with Docker Desktop (Windows, Mac or Linux)

Everything below uses invented data and development-only passwords. Run it from the repository folder.

1. Start Docker Desktop and wait until it says it is running.
2. Start the database and the API (the first run builds the image and takes a few minutes):
   `docker compose --env-file infrastructure/dev.env -f infrastructure/docker-compose.yml up --build`
   Leave this window open. It is ready when `http://localhost:8000/health` shows `{"status":"ok"}`.
3. In a second window, create the demo clinic, users and patient:
   `docker compose --env-file infrastructure/dev.env -f infrastructure/docker-compose.yml exec api python -m app.cli demo-seed`
   It prints the sign-in details (organisation `demo-clinic`, password `Demo-pass-2026!`; users `admin`, `doctor`, `nurse`, `reception`, `pharmacist`, `lab` at `@demo.example.com`). Running it again changes nothing.
4. Look at the API: open `http://localhost:8000/docs`, use `POST /api/v1/auth/login` with the details above, then paste the token under "Authorize".
5. Run the mobile app against it: in `apps/mobile`, `npm install`, then set `EXPO_PUBLIC_API_URL` to `http://10.0.2.2:8000` for an Android emulator, or `http://<your computer's address on the Wi-Fi>:8000` for a phone on the same network (allow port 8000 through the Windows firewall), then `npx expo start`. The microphone is simulated in this mode: it plays a scripted sample conversation, not your voice.
6. Walk through a visit: sign in as reception, find "Demo Patient", check in, record consent (recording and AI); sign in as the nurse for triage; sign in as the doctor, open the consultation, switch on AI assistance on the Conversation tab, Start, then Stop. The "Draft EMR" tab opens with what the built-in test extractor found.

To use Sarvam speech and the real language model: copy `infrastructure/dev.env` to `infrastructure/dev.local.env` (git ignores it), add `AAROGYA_SARVAM_API_KEY=...`, `AAROGYA_SPEECH_PROVIDER=sarvam` and `AAROGYA_LLM_PROVIDER=sarvam`, and use `--env-file infrastructure/dev.local.env` in the commands above. Sarvam sends audio and text to Sarvam's servers: use invented content only. The real microphone needs a development build, not Expo Go (see DEVICE_TEST_PLAN.md).

To stop: `Ctrl+C` in the first window. To wipe the data and start again: `docker compose --env-file infrastructure/dev.env -f infrastructure/docker-compose.yml down -v`.

Written without being able to run Docker here; the compose file, the seed command and the migrations were checked separately, so report the first thing that does not work.

## Docker
`docker compose --env-file .env -f infrastructure/docker-compose.yml up --build`
(untested in the Phase 1 build environment, which had no Docker daemon).

## Speech development
`AAROGYA_SPEECH_PROVIDER` defaults to `development` outside production (scripted synthetic transcripts; refused in
production). To exercise the real WebSocket stack end to end against a running server:
`python scripts/smoke_recording.py http://127.0.0.1:8765` (see the script header). Schedule
`python -m app.cli purge-audio` wherever audio retention is enabled. In dev builds the app uses simulated audio
(`EXPO_PUBLIC_SIMULATED_AUDIO=1` enables it in other builds). Set `EXPO_PUBLIC_USE_MICROPHONE=1` in a development or release build (not Expo Go) to use the real microphone, which is unit-tested but has never run on a device: see DEVICE_TEST_PLAN.md. Real speech and LLM providers need `AAROGYA_SARVAM_API_KEY` / `AAROGYA_ANTHROPIC_API_KEY` (see `.env.example`).

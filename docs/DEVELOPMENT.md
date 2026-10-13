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

## Docker
`docker compose --env-file .env -f infrastructure/docker-compose.yml up --build`
(untested in the Phase 1 build environment, which had no Docker daemon).

## Speech development
`AAROGYA_SPEECH_PROVIDER` defaults to `development` outside production (scripted synthetic transcripts; refused in
production). To exercise the real WebSocket stack end to end against a running server:
`python scripts/smoke_recording.py http://127.0.0.1:8765` (see the script header). Schedule
`python -m app.cli purge-audio` wherever audio retention is enabled. In dev builds the app uses simulated audio
(`EXPO_PUBLIC_SIMULATED_AUDIO=1` enables it in other builds); real microphone streaming is not implemented.

# Development guide

For people changing the code. Setup is in `05-INSTALLATION-SETUP.md`; how to run tests is in `10-TESTING-GUIDE.md`. The design reasoning behind the rules below is in `04-TECHNICAL-DESIGN.md` and the decision records in `adr/`.

## Repository layout

```
apps/mobile/            Expo Router app (TypeScript, strict)
services/api/           FastAPI service, Alembic migrations, tests, helper scripts
infrastructure/         docker-compose.yml, dev.env, Postgres role init, backup scripts
docs/                   documentation, adr/ decision records, design/ screenshots
.github/workflows/      ci.yml
```

There is no root-level package manager workspace: the API and the app are installed separately.

## Working agreements

These come from the product's safety model and are checked in review.

- AI output never writes to the record by itself. New AI features produce candidates or suggestions that a clinician accepts, and accepting runs ordinary service code.
- Do not invent medical codes, drug facts, provider capabilities or tax rules. If a licensed source is missing, leave the field empty or say what cannot be checked.
- Authorisation is checked on the server. A hidden button in the app is not access control.
- Anything that holds patient content must not appear in logs, audit rows, events, metrics or error text. Use ids, types and field names.
- Clinical writes are never queued offline in the app.
- Every behaviour must still work when AI, speech and the network providers are off.
- Update the documentation in the same change. If you add an environment variable, an endpoint, a table or a permission, the matching document in this folder changes too.

## Backend conventions

The package is `app`; code style is enforced by ruff (line length 100, rules E, F, I, UP, B, S, C4) and `mypy --strict` with the Pydantic plugin. Tests relax a few security lint rules. A module under `app/modules/<area>` normally has `models.py` (SQLAlchemy 2 declarative), `schemas.py` or schemas inside the service file (Pydantic v2), `service.py` (business logic that takes a `Session` and a `Principal`) and `router.py` (thin FastAPI routes). Sessions are synchronous (ADR-0003). Services commit their own work and write an audit row for anything that touches patient data.

### Add an endpoint

1. Add the service function and its schemas. Fetch rows through the request's tenant-bound session; do not pass organisation ids around by hand beyond setting them on new rows.
2. Add the route in the module's `router.py` with `Depends(require("area:action"))`. If the permission is new, add it to the catalogue in `modules/identity/permissions.py` with a description, then grant it to the right roles in the same file.
3. If the router is new, include it in `app/main.py`.
4. Test it: the happy path, the role matrix (who is refused), and cross-tenant access.
5. If you changed or added a response model, regenerate the field list the app is checked against: `cd services/api && PYTHONPATH=. python scripts/export_contract.py`, and commit `apps/mobile/src/api/contract.json`. A backend test fails if it is stale, and a mobile test fails if a schema in `src/api/schemas.ts` requires a field the API does not return.
6. Add it to `07-API-DOCUMENTATION.md` (the endpoint index is regenerated from the routers; the prose sections are written by hand).

### Add a table or column

1. Change the model, then write a migration in `alembic/versions` (next number, `down_revision` set). Autogenerate can start you off, but review the output; the migrations here also create triggers, policies and indexes by hand.
2. For a tenant table, include `ENABLE` and `FORCE ROW LEVEL SECURITY` and the `tenant_isolation` policy, copied from a recent migration such as 0011 or 0013.
3. If rows must not change, add a guard trigger. For provenance-carrying clinical facts, reuse `guard_clinical_fact` as migration 0012 does.
4. Add the table to `TENANT_TABLES` in `tests/conftest.py` so tests start from a clean slate, and to `app/modules/identity/permissions.py` if it needs new permissions.
5. Run `alembic upgrade head` on an empty database and the full test suite. Update `08-DATABASE-DESIGN.md`.

### Configuration

Add the field to `Settings` in `app/core/config.py` (prefix `AAROGYA_` is automatic), put a safe development default or require it in production, add it to `.env.example` if people commonly set it, and add it to `06-CONFIGURATION.md`.

### Providers

Speech providers implement the interface in `app/speech/provider.py` and register in `main.py` only when configured; language-model providers implement `app/ai/llm.py`. A provider must never log request or response content, and must have a fake or stub for tests, since the suite never calls a real vendor. Adding a vendor also means a row in the clinical safety log and in the security document about data processing.

## Mobile conventions

Routes are files under `src/app` (Expo Router). Screens live in `src/features/<area>`. Put anything that can be tested without React into `src/domain` and give it a test in `src/domain/__tests__`. API access goes through `src/api`: add a zod schema in `schemas.ts` and a function in `endpoints.ts`; responses that do not match the schema fail visibly. The `@/` alias maps to `src`. Use the design-system tokens and components rather than ad hoc styles, and state failures in plain language. Lists that contain patient data use a zero cache time so they do not linger in memory.

Expo changes quickly. `apps/mobile/AGENTS.md` asks contributors, human or automated, to check the Expo documentation for the installed SDK (currently 58) before using an Expo API, instead of relying on memory.

## Checks before you push

```bash
# services/api
ruff check . && ruff format --check . && mypy app && pytest -q
# apps/mobile
npm run typecheck && npm test
```

CI (`.github/workflows/ci.yml`) runs the same on every push and pull request: the API job against a pgvector PostgreSQL service, plus `pip-audit` (advisory); the mobile job runs `npm ci`, type-check, tests, `npm audit` (advisory) and an Android export. A change that turns any non-advisory step red should not be merged.

## Decisions and documentation

Significant decisions get a short record in `docs/adr/` (status, context, decision, consequences). Clinical hazards go in `CLINICAL_SAFETY.md` with the control that addresses them. New open items go in `13-PRODUCT-BACKLOG.md`, not into comments in code. There are currently no `TODO` or `FIXME` markers in the source on purpose.

## Branches and reviews

Work happens on feature branches and lands through pull requests into `main`. Prefer merging `main` into a long-lived branch over rewriting its history. Pull request descriptions should say what was tested and, just as importantly, what was not; the existing ones are a good model.

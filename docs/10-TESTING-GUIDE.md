# Testing guide

## What exists

| Suite | Location | Size | What it covers |
|---|---|---|---|
| API tests | `services/api/tests` | 504 tests in 38 modules | Behaviour through the HTTP API against a real PostgreSQL database: authentication, role matrices, tenant isolation, the clinical workflow, immutability triggers, consent gate, audio gateway, speech and AI pipelines against fakes, guardrails, billing, FHIR, operations |
| Mobile tests | `apps/mobile/src/**/__tests__` | 18 suites, 142 tests | Pure logic (dosing shorthand, billing and tax arithmetic, EMR draft layout, worklists, print HTML, permissions, dates), the API client, the audio gateway and capture modules against fake backends |
| Type checks | `mypy app` (strict), `npm run typecheck` (strict) | | The whole API package and the whole app |
| Lint and format | `ruff check`, `ruff format --check` | | API code and tests |
| Evaluation fixtures | `services/api/evals` | 2 files | Tiny synthetic gold sets for the extraction evaluation harness |
| Live check scripts | `services/api/scripts` | 6 scripts | Manual checks against real Sarvam services, a smoke test of the real WebSocket stack, a load generator. Not part of CI |

## Running the API tests

The tests need a PostgreSQL superuser, because the suite creates its own database (`aarogya_test`) and a non-superuser role that the application connects as. Using a superuser for the application would bypass row-level security and make the isolation tests meaningless, so the harness connects the application as a separate non-superuser role instead.

```bash
cd services/api
. .venv/bin/activate
export AAROGYA_TEST_ADMIN_URL=postgresql+psycopg://postgres@localhost:5432/postgres   # the default
ruff check . && ruff format --check . && mypy app
pytest -q
```

The full suite takes about 8 to 10 minutes on a four-core machine. It runs migrations once for the session and truncates tenant tables between tests, using the `TENANT_TABLES` list in `tests/conftest.py`; a new tenant table must be added there. Useful variations: `pytest tests/test_billing.py -q` for one module, `pytest -k legal_hold` for a name match, `pytest --collect-only -q` to list tests.

Fixtures worth knowing: `client` (an in-process test client wired to the real application), `db` (a session with the tenant bypass set, for direct SQL checks), `org_a` and `org_b` (two organisations with administrators), and the visit builders in `tests/clinical_helpers.py` that create a checked-in patient with a full care team.

## Running the mobile tests

```bash
cd apps/mobile
npm ci            # or npm install
npm run typecheck
npm test
CI=1 npx expo export --platform android --output-dir /tmp/export
```

The export step proves the Android bundle compiles; it does not run the app.

## What the tests prove, and what they do not

The suite is strongest on the properties the product depends on. Tenant isolation is tested at the API and with direct SQL. Immutability is tested by trying to break it with raw SQL (for example, updating a signed prescription or deleting a credit note). Role matrices are tested per feature, including that billing staff are refused the clinical endpoints that the tests probe. Logs, audit rows and events are checked for the absence of clinical text. The AI guardrails have tests for quote matching, hedging, denial, injection text and unknown speakers. Billing arithmetic, rounding and the freeze rules are tested on both sides, in Python and in TypeScript.

The suite does not prove: that the Sarvam adapter, the Anthropic adapter or the microphone module work against the real world (they are tested against fakes; the manual scripts have been run once for Sarvam only); that the mobile screens render or behave correctly (there are no component or screen tests and no end-to-end tests; screen behaviour was checked by hand in a browser build); that speech or extraction accuracy is acceptable on real Indian-language clinical audio (the evaluation fixtures are synthetic); that the Docker image builds or the stack works under load, behind a proxy, or with several containers; or that the system resists attack (no penetration test).

## Known gaps in test coverage

Coverage is not measured; `pytest-cov` and a mobile coverage threshold are not configured. Specific gaps:

- No screen, navigation or accessibility tests for the mobile app, and none on a device.
- No contract test tying the zod schemas in `apps/mobile/src/api/schemas.ts` to the API's OpenAPI document. A server field rename would be caught by the app only at runtime.
- Migration downgrades are not tested, and no test upgrades a populated database from an older revision.
- FHIR bundles are validated with the `fhir.resources` R4B models, not with the HL7 validator; there is no profile validation.
- The load test has been run once, on a development machine, without login, AI or audio.
- Multi-worker behaviour (the in-memory live transcript hub and rate limiters) is untested because it is known not to work across processes.
- The backup and restore-drill scripts have been run by hand, not in CI.
- No automated prompt-injection corpus beyond a handful of cases.

## Manual verification checklists

`DEVICE_TEST_PLAN.md` covers the microphone and Sarvam on real devices, with acceptance criteria for a pilot. `SARVAM.md` lists the live checks for translation, read-aloud and chat. `CLINICAL_SAFETY.md` lists, per hazard, the control that should be tested and what is still open. `OPERATIONS.md` describes the restore drill, which should be run monthly once there is a real environment.

## Dependency scanning

CI runs `pip-audit` and `npm audit` as advisory steps. The known npm findings are in build and test tooling pulled in by the Expo SDK; the details are in `OPERATIONS.md`.

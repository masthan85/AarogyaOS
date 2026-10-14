# AarogyaOS

AI-native clinical operating system for Indian clinics and hospitals. AarogyaOS follows a
patient from arrival to follow-up, turning consented, clinician-supervised conversations
into structured, reviewable clinical information. AI supports clinicians; it never
decides for them, and every workflow works with AI switched off.

**Status:** Phases 0-7 done to the extent possible without infrastructure (FHIR export only, no ABDM integration; see docs/OPERATIONS.md for what is not done): architecture, platform, patients, scheduling and queue, the clinical record, the consent-and-recording pipeline, clinician-reviewed clinical AI, and a read-only FHIR R4 export. A Sarvam speech adapter, a Claude LLM adapter and microphone streaming are written but have never been run against the live services or on a device (see docs/DEVICE_TEST_PLAN.md); synthetic development providers remain the default and are refused in production, and no drug or terminology database is connected.
No AI extraction or suggestions exist yet — see [docs/BACKLOG.md](docs/BACKLOG.md).

| Path | What |
|---|---|
| `apps/mobile` | React Native (Expo Router, TypeScript strict) |
| `services/api` | FastAPI modular monolith, PostgreSQL with row-level security |
| `infrastructure` | Docker Compose for local development |
| `docs` | Architecture, security, clinical safety, ADRs |

Start with [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

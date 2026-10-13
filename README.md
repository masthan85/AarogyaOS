# AarogyaOS

AI-native clinical operating system for Indian clinics and hospitals. AarogyaOS follows a
patient from arrival to follow-up, turning consented, clinician-supervised conversations
into structured, reviewable clinical information. AI supports clinicians; it never
decides for them, and every workflow works with AI switched off.

**Status:** Phases 0-4 done: architecture, platform, patients, scheduling and queue, the clinical record, and the consent-and-recording pipeline. No real speech vendor is integrated yet (a synthetic development provider drives the pipeline); no AI extraction exists yet.
No AI extraction or suggestions exist yet — see [docs/BACKLOG.md](docs/BACKLOG.md).

| Path | What |
|---|---|
| `apps/mobile` | React Native (Expo Router, TypeScript strict) |
| `services/api` | FastAPI modular monolith, PostgreSQL with row-level security |
| `infrastructure` | Docker Compose for local development |
| `docs` | Architecture, security, clinical safety, ADRs |

Start with [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

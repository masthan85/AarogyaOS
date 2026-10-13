# Initial Backlog

P1 Foundation (this phase): repo, API skeleton, config, DB+Alembic, identity, tenancy,
RBAC, audit/outbox, tenant+permission tests, mobile shell, Docker, CI.
P2 Patients (done): registration, duplicate detection, minimal-field search, appointments, check-in, walk-ins,
queue, timeline, encrypted ABHA identifier field, practitioners and working hours.
P2 follow-ups: patient photo (needs object store, Phase 4), duplicate merge workflow, admin UI for practitioners
and working hours (API exists), search rate limiting, ABHA verification via ABDM (Phase 6), push reminders.
P3 EMR: encounters, triage/vitals, conditions, allergies, medications, notes,
investigations, prescriptions (drafts+sign), follow-up.
P4 Speech: consent, sessions, audio capture, gateway, SpeechProvider, Sarvam adapter
(after verification), diarisation, transcript UI, speaker correction.
P5 AI: extraction, clinical state, suggestions, safety checks, RAG, review UI, evals.
P6 Interop: FHIR facade, ABDM adapters (after sandbox access).
P7 Hardening: observability, backup/DR, load, cost dashboards, admin, deployment.

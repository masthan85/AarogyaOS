# Initial Backlog

P1 Foundation (this phase): repo, API skeleton, config, DB+Alembic, identity, tenancy,
RBAC, audit/outbox, tenant+permission tests, mobile shell, Docker, CI.
P2 Patients (done): registration, duplicate detection, minimal-field search, appointments, check-in, walk-ins,
queue, timeline, encrypted ABHA identifier field, practitioners and working hours.
P2 follow-ups: patient photo (needs object store, Phase 4), duplicate merge workflow, admin UI for practitioners
and working hours (API exists), search rate limiting, ABHA verification via ABDM (Phase 6), push reminders.
P3 EMR (done): encounters with triage → consultation, vitals with flags, notes, diagnoses, allergies, medicine
history, investigations with structured results, prescriptions with safety check and signing, follow-ups, clinical
state and alerts, verification workflow, database-level immutability.
P3 follow-ups: clinical sign-off of reference ranges and paediatric ranges, medication knowledge provider (interactions,
contraindications, dose checks, Indian brand/generic data under licence), terminology service (ICD/SNOMED/LOINC),
document/PDF result upload (needs object store), prescription print/PDF and patient copy, referrals, care-team
scoping and break-glass, doctor handover/cover, edit-draft UI for prescriptions, results-to-review dashboard tile,
FHIR mapping of the clinical record.
P4 Speech (done, provider-independent): consent (8 purposes, versioned wording, guardians), recording sessions,
authenticated audio gateway, SpeechProvider + registry + fallback + development provider, immutable transcripts
with language/code-switch/speaker metadata, speaker assignment, audio retention + purge, usage metering, speech
eval tools, mobile consent/recording UI. **Open:** Sarvam adapter (needs live API docs + key), native microphone
streaming module + device tests, real-language evaluation set, Redis for multi-worker partials/guards, scheduled
purge job, legal review of consent wording, transcript text-correction layer.
P4 (original scope): consent, sessions, audio capture, gateway, SpeechProvider, Sarvam adapter
(after verification), diarisation, transcript UI, speaker correction.
P5 AI: extraction, clinical state, suggestions, safety checks, RAG, review UI, evals.
P6 Interop: FHIR facade, ABDM adapters (after sandbox access).
P7 Hardening: observability, backup/DR, load, cost dashboards, admin, deployment.

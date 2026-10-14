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
eval tools, mobile consent/recording UI. Sarvam adapter built from the vendor SDK (fake-server tested; live run pending). Microphone streaming module integrated (fake-backend tested; device test plan written). **Open:** device run of the microphone
streaming module + device tests, real-language evaluation set, Redis for multi-worker partials/guards, scheduled
purge job, legal review of consent wording, transcript text-correction layer.
P4 (original scope): consent, sessions, audio capture, gateway, SpeechProvider, Sarvam adapter
(after verification), diarisation, transcript UI, speaker correction.
P5 AI (done, provider-independent): extraction with guardrails, review queue, accept/edit/reject into facts with
provenance, deterministic and model suggestions, approved-knowledge retrieval with two-person approval, patient
summary, usage metering, evaluation harness, mobile Assist tab. Anthropic adapter built (stub-tested, not run live). **Open:** run the LLM adapter live, DPA, residency
decision and a clinician-labelled eval set, real embeddings and pgvector, translation provider, terminology
service, medication knowledge provider (interactions/contraindications/dose), consultation summary and
patient-summary drafting by model, differential/medication suggestions evaluated against clinician-labelled cases,
automatic prompt-injection test corpus, per-category suggestion thresholds, mobile jest/UI tests for the Assist
screen beyond pure logic, device testing.
P6 Interop (FHIR part done): read-only base-R4 export of a completed visit as a document Bundle, with provenance tags,
exclusions and audit. **Open (needs the ABDM IG and sandbox access):** profile conformance and `meta.profile`,
HL7 validator in CI, ABHA create/verify, consent manager and consent artefacts, HIP/HIU flows, HPR/HFR registration,
terminology service for coded diagnoses and medicines, FHIR search/read for more resources, Provenance resources,
registered identifier systems.
P7 Hardening (partly done, see OPERATIONS.md): readiness with migration check, Prometheus metrics without identifiers,
security headers and request-size cap, production config rules, scheduled jobs with locking and a ledger, optional
pgvector search, encrypted backup + restore drill (run), load-test script (run once), dependency scanning in CI,
migrations moved out of container start. **Open:** Redis hub for multi-container audio/partials, S3-compatible encrypted
audio store + KMS, field-key rotation, PITR/WAL archiving and RPO/RTO targets, tracing and log shipping, dashboards and
alerts, AI cost configuration, Kubernetes/Terraform, image build verification, TLS/WAF, login rate limiting, pen test,
Expo SDK upgrade to clear audit findings, admin console, capacity test on a production-like stack.

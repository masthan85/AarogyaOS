# AarogyaOS — Architecture (Phase 0)

Status: Phase 0 baseline. Items marked **[VERIFY]** depend on external facts that
must be confirmed from authoritative documentation before implementation.

## 1. Understanding of AarogyaOS

AarogyaOS is an operating layer for the patient's care journey in Indian clinics and
hospitals. Every authorised interaction between a patient and staff is a
**Clinical Interaction Session** with explicit identity, encounter, purpose, consent
and Start/Stop. Speech from those sessions is converted to *candidate* structured
information. Candidates become part of the **Patient Clinical State** only after a
human with the right role verifies them.

The product spine:

```
Patient Journey → Encounter → Clinical Interaction → Transcript (raw + normalised)
→ Extraction candidates → Patient Clinical State → AI Suggestions
→ Clinician review → Clinical action → Longitudinal record (+ audit trail)
```

Non-negotiables:

1. AI is decision support. It never diagnoses, prescribes, orders, refers or discharges.
2. The complete workflow works with every AI/speech dependency switched off.
3. Recording only happens inside a consented, identified, purposeful session.
4. Raw transcript is never discarded; normalised text is derived, never a replacement.
5. Provenance and verification state exist on every clinically material fact.
6. Authorisation and tenant isolation are enforced on the backend.
7. Minimum necessary data; simplest architecture that meets the requirement.

## 2. MVP definition

In: auth, multi-tenancy, RBAC, patient registration/search, appointments, check-in,
queue, consent, triage/vitals, timeline, encounter, interaction sessions with live
transcription, SpeechProvider abstraction (+ Sarvam adapter once verified),
extraction, structured note, AI suggestions with accept/edit/reject, conditions,
allergies, medications, investigation and prescription drafts with doctor
signing, follow-up, patient summary, audit logs, basic administration.

Out (see section 21): LIS/RIS/PACS, pharmacy inventory, insurance/TPA, IPD, ICU, OT,
telemedicine, remote monitoring, full patient app, analytics, research.

## 3. End-to-end patient journey

| Stage | Actor | Key records | Events |
|---|---|---|---|
| Arrival / search | Receptionist | Patient lookup (minimal-fields search) | — |
| Registration | Receptionist | Patient, PatientIdentifier, language prefs | PATIENT_REGISTERED |
| ABHA linkage [VERIFY] | Receptionist | PatientIdentifier(ABHA) | PATIENT_UPDATED |
| Appointment / walk-in | Receptionist | Appointment | APPOINTMENT_BOOKED |
| Check-in, token | Receptionist | QueueEntry | PATIENT_CHECKED_IN |
| Consent | Receptionist/Nurse | Consent (per purpose, versioned) | CONSENT_GRANTED |
| Triage, vitals | Nurse | Observation, Vital | TRIAGE_STARTED, VITAL_RECORDED |
| Consultation | Doctor | Encounter, Interaction, Transcript, Note | ENCOUNTER_STARTED, RECORDING_* |
| Investigations | Doctor → Lab/Radiology | ServiceRequest, DiagnosticReport | INVESTIGATION_ORDERED, RESULT_RECEIVED |
| Diagnosis, prescription | Doctor | Condition, MedicationRequest | DIAGNOSIS_CONFIRMED, PRESCRIPTION_SIGNED |
| Pharmacy, billing | Pharmacist, Billing | Dispense, Invoice, Payment | later phases |
| Follow-up | Doctor / Coordinator | FollowUp | FOLLOWUP_CREATED |
| Close | Doctor | Encounter, patient summary | ENCOUNTER_COMPLETED |

Every transition writes an immutable `ClinicalEvent` (outbox pattern) and, where
data is accessed or changed, an `AuditLog` row.

## 4. Mobile architecture

React Native + TypeScript (strict) + Expo (dev client; custom native modules allowed),
Expo Router. Android-first, iOS-compatible, tablet-responsive (doctor landscape
consultation uses a 3-pane layout: context | consultation | copilot).

Layers (dependency direction downward only):

```
app/ (routes)            presentation shell
features/<name>/         screens, hooks, feature components
domain/                  pure types, rules (no React, no I/O)
api-client/ (package)    typed HTTP + SSE/WebSocket clients, Zod validation
services/                device: secure-store, audio, biometrics, push, connectivity
state/                   TanStack Query (server state), small per-feature stores
design-system/ (package) tokens + reusable components
```

No global store. Server state lives in TanStack Query; local state in feature hooks;
drafts persisted in an encrypted outbox. Tokens only in Keychain/Keystore via
`expo-secure-store`. Offline: idempotent write queue limited to *safe* operations
(drafts, vitals entry awaiting submit, check-in notes); clinically critical actions
(signing prescriptions, confirming diagnoses) require connectivity. Recording audio
is buffered locally if the stream drops, but never extracted until reconnected.

## 5. Backend architecture

Modular monolith (FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL 16,
Redis, S3-compatible storage; pgvector from the AI phase).

```
services/api/app/
  core/          config, db, security, errors, logging, deps
  modules/       identity, tenancy, audit, patients, scheduling, consent,
                 encounters, clinical, interactions, ai, fhir, billing
                 each: models.py, schemas.py, service.py, router.py
  providers/     speech/, llm/, embedding/, translation/, terminology/, knowledge/
  integrations/  abdm/, fhir/
```

Rules: routers are thin; services own business logic and call `authorize()`;
modules talk through service interfaces, not each other's tables; every table
carries `organisation_id` and every query is scoped through a tenant-bound
repository/session helper. Postgres row-level security is added as defence in depth
(ADR-004). The clinical-AI and speech code are separate packages under `app/` with
no import from request-handling code, so they can later be extracted without a rewrite.

## 6. Speech AI architecture
See `SPEECH_ARCHITECTURE.md`.

## 7. Multilingual and dialect strategy

- Language metadata is **data, not code**: a `languages` table (BCP-47 tag, script,
  display names, provider support matrix, enabled flag). New languages are rows.
- Never trust a single language label. Each segment stores `language`,
  `secondary_language`, `language_confidence`, and `code_switch` spans.
- Clinical normalisation operates on the raw transcript with the *patient's
  language profile* as a hint, not a constraint.
- Dialect/accent quality is measured per language/region cohort in the evaluation
  harness; routing and fallback decisions use measured WER, not marketing claims.
- Transliteration (Roman-script Telugu etc.) and native script are both stored.
- Medical terms in English inside regional speech are matched via a terminology
  lexicon of (surface form variants → concept), expanded from reviewed data only.

## 8. Sarvam strategy
See `SPEECH_ARCHITECTURE.md` §Sarvam. In short: adapter behind `SpeechProvider`,
selected by `SPEECH_PROVIDER`, built only after capabilities, retention terms and
pricing are verified against official docs; fallback provider configurable.

## 9. Clinical AI architecture
See `AI_ARCHITECTURE.md`.

## 10. Patient Clinical State
Defined in `AI_ARCHITECTURE.md` §Clinical State and `DATA_MODEL.md`. Every fact has
`source` and `verification_state`. AI-extracted facts enter as `AI_GENERATED` /
`REQUIRES_REVIEW` and never feed deterministic safety checks as confirmed until a
clinician confirms (safety checks additionally run on *unconfirmed* allergies
conservatively — warn, never assume safe).

## 11. Database / domain model
See `DATA_MODEL.md`.

## 12. API architecture

Versioned REST under `/api/v1`, OpenAPI generated by FastAPI. Conventions: UUID ids,
cursor pagination, `Idempotency-Key` on mutating POSTs, RFC 7807-style errors with
correlation id, optimistic concurrency via `version`. Realtime: SSE for transcript and
suggestion events to the doctor screen; WebSocket for audio upload (mobile → gateway).
FHIR facade under `/api/v1/fhir` is generated from domain objects (read-only first).

## 13. Security model
See `SECURITY.md`.

## 14. Consent and recording model

Separate `Consent` records per purpose: `MEDICAL_CARE`, `AUDIO_RECORDING`,
`SPEECH_TRANSCRIPTION`, `AI_PROCESSING`, `AUDIO_RETENTION`, `RESEARCH`, `ANALYTICS`,
`AI_MODEL_IMPROVEMENT`. Each: patient (or representative with relationship),
policy version, status (GRANTED/WITHDRAWN/EXPIRED), timestamps, capturing staff,
method. Starting a session requires, at minimum: identified patient, open
encounter, authenticated authorised staff, declared purpose, and active
AUDIO_RECORDING + SPEECH_TRANSCRIPTION consent (+ AI_PROCESSING for extraction).
The server enforces this; the audio gateway re-checks consent on connect and on
withdrawal terminates the stream. Organisation policy decides audio retention
(`DISCARD_AFTER_TRANSCRIPTION`, `RETAIN_DAYS=n`, `RETAIN_CLINICAL`); transcripts and
records have separate retention.
**[LEGAL REVIEW]** Validity of representative consent, minors, and withdrawal
semantics under the DPDP Act 2023 and its rules must be confirmed with counsel.

## 15. FHIR / ABDM strategy

The operational model is separate from FHIR. A mapping layer (`integrations/fhir`)
renders FHIR R4 resources conforming to the **NRCeS FHIR IG for ABDM** (current
published: v2.0.1) with `meta.profile` set. ABDM gateway/HIP/HIU flows go behind
adapter interfaces; real endpoints are added only after sandbox access and
verification of official specs. No ABDM endpoint is hardcoded or guessed.

## 16. Screen map

Auth: Splash → Login → Organisation selection → Role dashboard.
Reception: Patient search, New patient, Appointments, Queue, Check-in, Consent, Billing.
Nurse: Queue, Triage, Vitals, Interaction (optional).
Doctor: Dashboard, Doctor calendar, Patient profile + timeline, Consultation
(Context | Live conversation + Note | AI Copilot), Diagnosis, Investigations,
Prescription, Reports, Follow-up, Patient summary.
Admin: Organisation/facility/department, Staff & roles, Policies (recording, consent,
retention, AI), Languages, Audit viewer.
Common: Notifications, Profile, Settings.

## 17. Repository structure

```
/apps/mobile                 React Native app (Expo Router)
/services/api                FastAPI modular monolith
/services/clinical-ai        (Phase 4–5) speech & AI workers, extractable
/packages/shared-types       generated from OpenAPI
/packages/api-client
/packages/design-system
/infrastructure              docker-compose, deployment manifests
/docs  /docs/adr
/tests                       cross-service e2e
/scripts
```

## 18. Development phases
0 foundation docs → 1 platform foundation → 2 patient workflow → 3 clinical EMR →
4 speech → 5 clinical AI → 6 interoperability → 7 productionisation.

## 19. Initial backlog
See `BACKLOG.md`.

## 20. Major risks

| Area | Risk | Mitigation |
|---|---|---|
| Clinical | Hallucinated or over-confident AI facts | Candidate-only extraction, provenance, schema validation, deterministic safety layer, clinician gate |
| Clinical | Alert fatigue / automation bias | Few, categorised, ranked suggestions; measure edit/reject rates |
| Clinical | Mis-heard negation/dose/drug in Indian languages | Per-language eval, confidence display, mandatory review for meds/allergies |
| Privacy | Recording without valid consent; DPDP obligations | Server-enforced consent gate; retention policy; legal review |
| Security | PHI leakage via logs, analytics, push, third-party AI | PHI-free logging, lock-screen-safe pushes, DPA with providers, data residency check |
| Security | Cross-tenant access | tenant-scoped repos + RLS + explicit isolation tests |
| Technical | Poor audio / code-switching accuracy | Provider abstraction, fallback, measured routing |
| Technical | Connectivity gaps | Safe offline queue, AI optional |
| Regulatory | CDSCO software-as-medical-device status; NMC rules; telemedicine | Early regulatory review before pilot |
| Commercial | Per-minute speech cost vs Indian price points | Cost metering from day one; retention/mode tuning |

## 21. Not in MVP
LIS/RIS/PACS, pharmacy inventory, insurance/TPA, IPD/beds, ICU/OT, emergency,
telemedicine, remote monitoring, full patient app, population analytics, research,
model training on customer data, autonomous AI actions of any kind, Kafka,
microservices.

## 22. Reversible decisions
Speech/LLM/embedding provider; ASR routing; vector store (pgvector → dedicated);
object store vendor; SSE vs WebSocket for downlink; Expo managed vs bare;
monolith → extracted AI service; RLS strictness; terminology vendor.
Hard-to-reverse (decide carefully): UUID ids, tenant column on every table,
event/provenance model, consent model shape, auth token design.

## 23. Phase 1 plan
Scaffold monorepo → backend (config, DB, Alembic, structured logging, correlation
ids) → identity (users, argon2id passwords, JWT access + rotating refresh with
reuse detection, MFA-ready fields) → tenancy (organisation, facility, department)
→ RBAC (role/permission seed, `require_permission`) → audit framework + clinical
event outbox → tests incl. tenant isolation and permissions → mobile shell (Expo
Router, secure token storage, login, org selection, role dashboard, design-system
primitives) → Docker Compose, CI, docs. Exit criteria: all tests, lint, types,
migrations and mobile typecheck pass.

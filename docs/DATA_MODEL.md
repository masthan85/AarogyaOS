# Data Model

Conventions: UUID v4 primary keys; `organisation_id` NOT NULL on every tenant table;
`created_at/updated_at` UTC `timestamptz`; `version` integer for optimistic
concurrency; clinical rows are append-only (corrections create a new row linked via
`supersedes_id`; nothing is overwritten silently); soft-delete via status, never
hard-delete clinical data.

## Phase 1 tables (implemented)
organisations, facilities, departments, users, user_roles (user ↔ role per
organisation/facility), roles, permissions, role_permissions, refresh_tokens
(hashed, family id, rotation + reuse detection), audit_logs, clinical_events
(outbox).

## Planned (by phase)
3 encounters, observations/vitals, conditions, allergies, medications,
medication_requests/prescriptions, service_requests, diagnostic_reports,
clinical_notes, follow_ups, documents
4 consents, consent_policies, clinical_interactions, audio_assets, transcripts,
transcript_segments, languages
5 ai_extractions, ai_suggestions, ai_suggestion_actions, ai_usage
7 invoices, payments, billing items

## Phase 2 tables (implemented)
patients, patient_identifiers (AES-GCM ciphertext + HMAC blind index; masked hint), patient_languages,
patient_revisions (previous values of changed demographics), mrn_counters, practitioners, working_hours,
appointments, queue_entries, queue_counters.

Notes: mobile numbers are stored E.164 and are deliberately **not unique** (families share numbers);
age-only registration stores 1 January of the implied birth year with `dob_is_estimated = true`;
the database rejects overlapping scheduled appointments per practitioner with an `EXCLUDE USING gist`
constraint; tokens are issued per facility per local day from a locked counter.

## Phase 3 tables (implemented)
encounters (one per appointment; TRIAGE → IN_PROGRESS → COMPLETED), observations, clinical_notes, conditions,
allergies, patient_medications, prescriptions + prescription_items, service_requests, investigation_results,
follow_ups.

Facts (observations, notes, conditions, allergies, medication history) share the provenance columns below and are
**append-only**: a database trigger rejects any update except `is_current` and the verification bookkeeping columns,
and any delete. Corrections insert a new row linked by `supersedes_id`. Signed prescriptions (and their items) and
reported results are likewise frozen by triggers; the only permitted change to a signed prescription is voiding.
`audit_logs` is append-only by trigger. Codes (ICD/SNOMED/LOINC) are nullable and only accepted together with a code
system; nothing is auto-coded.

## Phase 4 tables (implemented)
languages (global catalogue), consent_policies (versioned wording; frozen once published, can only be retired),
consents (append-only decisions; only withdrawal fields may change; a withdrawn consent is final),
clinical_interactions (recording sessions), interaction_speakers (provider label -> human-assigned role),
transcript_segments (immutable), audio_assets (only when retention is allowed; storage_key NULL once deleted),
speech_usage (metering, no content). Organisation settings gain a validated `policy` object (recording, AI,
audio retention, enabled languages, guardian age). The brief's separate `transcripts` table is folded into
`clinical_interactions` + `transcript_segments` (one transcript per session): see ADR-0006.

## Phase 5 tables (all tenant-scoped with forced RLS)
`ai_extractions` (one row per model run: range of segments, prompt version, provider/model, kept/dropped counts,
status; no text), `ai_candidates` (the review queue: kind, text, assertion, evidence quotes with segment ids,
risk flags; only the review columns can change, and only once), `ai_suggestions` + `ai_suggestion_actions`
(append-only decision history), `ai_usage` (metering, no content), `knowledge_documents` (only the approval and
retirement columns change) + `knowledge_chunks` (embeddings as float arrays), `patient_summaries` (versioned;
approved rows are frozen and may only become SUPERSEDED). Immutability is enforced by triggers, not only by code.

## Templates and letters
`cover_arrangements` (tenant-scoped, forced RLS, migration 0008): one doctor asking a colleague to review their results between two dates (at most 31 days). It only widens the colleague's results-awaiting-review list.

`note_templates` (tenant-scoped, forced RLS): an organisation's note layouts, as ordered sections that name a note type, a heading and a hint. Structure only; no pre-filled text. `patient_summaries` gained `kind` (`VISIT_SUMMARY` | `REFERRAL_LETTER`) and `recipient`; versions and supersession are per kind (and per recipient for letters), and the frozen-once-approved trigger covers both.

## Clinical fact mixin
`source`, `verification_state`, `certainty`, `recorded_by`, `recorded_at`,
`evidence_segment_ids`, `supersedes_id`.

## FHIR
Separate mapping layer; resources never stored as the source of truth.

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
2 patients, patient_identifiers, patient_language_preferences, practitioners,
appointments, queue_entries
3 encounters, observations/vitals, conditions, allergies, medications,
medication_requests/prescriptions, service_requests, diagnostic_reports,
clinical_notes, follow_ups, documents
4 consents, consent_policies, clinical_interactions, audio_assets, transcripts,
transcript_segments, languages
5 ai_extractions, ai_suggestions, ai_suggestion_actions, ai_usage
7 invoices, payments, billing items

## Clinical fact mixin (Phase 3+)
`source`, `verification_state`, `certainty`, `recorded_by`, `recorded_at`,
`evidence_segment_ids`, `supersedes_id`.

## FHIR
Separate mapping layer; resources never stored as the source of truth.

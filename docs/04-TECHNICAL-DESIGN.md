# Technical design

This document explains how the main mechanisms work, so that someone changing them knows which invariants they must keep. It complements `03-SYSTEM-ARCHITECTURE.md` (the shape of the system) and `08-DATABASE-DESIGN.md` (the tables). Statements here were checked against the code in `services/api/app` and `apps/mobile/src`.

## Identity, tokens and passwords

Passwords are hashed with Argon2id. A successful login returns a short-lived JWT access token (15 minutes by default, configurable from 1 to 60) carrying the user id, organisation id and session id, plus an opaque refresh token. Refresh tokens are stored only as hashes, belong to a family, and rotate on every use; presenting an already-rotated token revokes the whole family, which is how a stolen refresh token is detected. Accounts lock for 15 minutes after five failed attempts. Login attempts are also rate limited per client address, and patient search per user (60 a minute each by default, held in worker memory). Two-step sign-in is optional per user. Enrolment (`/auth/mfa/enroll`, then `/auth/mfa/confirm`) creates a TOTP secret (RFC 6238, implemented in `app/core/totp.py` without a third-party library), stored encrypted with the user id as authenticated data, and returns eight single-use recovery codes whose SHA-256 hashes are kept. Once on, login needs `mfa_code` after the password. Each accepted time step is recorded so a code cannot be replayed, a wrong code counts towards the lockout like a wrong password, a recovery code is spent when used, and an administrator can reset a colleague who has lost both phone and codes (audited). There is no QR code: the app shows the key as text. The mobile app can add a local biometric unlock in front of a stored session.

## Authorisation

Permissions are strings such as `patient:read` or `billing:adjust`, defined in one catalogue (`modules/identity/permissions.py`) together with the role-to-permission map. `sync_reference_data` copies the catalogue into the `permissions`, `roles` and `role_permissions` tables, and runs through `python -m app.cli seed`, which every release must run after migrating. Endpoints declare `Depends(require("..."))`. Beyond the permission, several rules are object-level and live in services: only the encounter's own doctor writes clinical content (`require_owner`), transcripts are readable only by the person who recorded them and, for clinical sessions, the encounter's doctor, and reference documents must be approved by someone other than their creator.

## Tenancy

See the request path in `03-SYSTEM-ARCHITECTURE.md`. In code, `core/db.py` provides `set_tenant(session, org_id, bypass=False)`, which sets the PostgreSQL settings the policies read. Test helpers and jobs use the bypass explicitly. A new tenant table needs three things in its migration: an `organisation_id` column, `ENABLE` plus `FORCE ROW LEVEL SECURITY`, and the standard `tenant_isolation` policy. The test fixture's list of tenant tables must also include it so data is cleaned between tests.

## Provenance and verification

Every clinical fact has a `source` (patient reported, staff entered, doctor entered, device recorded, lab result, external record, AI extracted) and a `verification_state` (unverified, requires review, clinician confirmed, clinician edited, clinician rejected). Clients may only claim the human sources; device, lab and AI sources are set by the server. A doctor's own entry is stored as clinician confirmed; anyone else's is unverified until a doctor confirms it through the generic verify endpoint. Diagnoses, procedures, vaccines and referrals need a doctor to confirm or reject. Editing a fact inserts a new row that points at the old one and flips the old row's `is_current` flag; the guard trigger allows nothing else to change. Safety checks treat unconfirmed allergies conservatively: they warn rather than assume absence.

## Consent and recording gate

Starting a session requires an identified patient, an open encounter (for clinical purposes), an authorised user and active consents for audio recording and transcription, plus AI processing if extraction is wanted. The check runs at session start, at WebSocket connect, and on a timer while streaming; withdrawal ends the stream. Reception sessions cannot produce clinical facts. Audio is discarded after transcription by default; retaining it needs both an organisation policy that allows it and the patient's retention consent, and retained audio is encrypted per chunk and has a purge date. The purge job removes expired audio and audio whose consent was withdrawn, and skips patients under a legal hold.

## Speech layer

`app/speech/provider.py` defines the provider interface; `registry.py` resolves the configured provider and an optional fallback. Final segments are stored with language, secondary language, confidence and code-switch information, plus a provider speaker label. A human maps speaker labels to roles (doctor, patient, family, other). Corrections never overwrite `raw_text`: `transcript_corrections` is append-only, the newest row for a segment applies, and the assistant reads the corrected text. The Sarvam adapter streams raw PCM, detects language per utterance and keeps the language hint off by default because a fixed hint produced Roman-script Hindi in a live test.

## AI extraction

The pipeline in `app/ai` builds a prompt (versioned, currently `extract-v2`) containing the transcript window as delimited data, asks the provider for strict JSON, and then runs guardrails on each item: the quote must appear verbatim in the cited line, questions are rejected, only allowed kinds and attributes survive, hedged speech becomes "possible", denials are kept, and an unknown speaker role raises a flag. Survivors become `ai_candidates` in the review queue; the extraction row records counts and the provider, never text. Accepting a candidate runs ordinary service code that creates the fact with source `AI_EXTRACTED` and the doctor as the confirming author. Rejections are kept. Only one decision is allowed per candidate, enforced by a trigger. Medication candidates can become a prescription draft but never a signed prescription. Evaluation fixtures and an evaluation harness exist, but the fixtures are tiny and synthetic.

Suggestions come in two kinds. Rule-based suggestions require no model. Model suggestions must cite approved reference passages retrieved from the organisation's knowledge library; a suggestion without a valid citation is dropped. Accepting an investigation suggestion creates a draft order only. The "ask the chart" feature answers a question about one patient from recorded entries and cites them, or says it found nothing; a keyword search over the chart is always available without AI.

## Code-built documents

Visit summaries, referral letters and the copy-as-text export are assembled by code from recorded facts. A model is never asked to write prose for these. The doctor edits and approves; approved versions are frozen and later changes create a new version. Translation, when enabled, produces a separate draft that is labelled as a draft for the doctor to check before approval.

## Prescriptions

A prescription is a draft with items (medicine name, strength, dose, route, frequency, duration, instructions). The safety check matches active allergies by name and states what it cannot check: interactions, contraindications and dose limits are not checked because no drug knowledge source is connected. Warnings must be acknowledged by code before signing. Signing freezes the prescription and its items (triggers), stores a safety snapshot and computes a seal: an HMAC-SHA256 over the prescription id, patient, encounter, practitioner, signer, signing time, notes and every item field, keyed from `AAROGYA_SEAL_KEYS` when set, otherwise from `AAROGYA_FIELD_ENCRYPTION_KEY`. `GET /prescriptions/{id}/integrity` recomputes it. This detects tampering in the database; it is not a legal digital signature. The mobile form includes a reader for Indian dosing shorthand (1-0-1, BD, TDS and similar) that only explains and never edits what was typed.

## Billing

Money is stored as whole paise in integers; the maximum on one line or invoice is one crore rupees, to catch typing slips. An invoice starts as a draft with up to 30 lines (quantity 1 to 999, tax rate 0 to 28 percent in basis points). Tax is computed per line, rounded half up, and added to the total. Issuing assigns the next `INV-nnnnnn` number from a locked per-organisation counter, freezes the total, the tax and the seller's GSTIN as it stood, and from then on database triggers allow only a transition to void. Payments are append-only, cannot exceed what is owed and can only be added to an issued invoice. A credit note reduces what the invoice is worth (numbered `CN-nnnnnn`), and a refund can return only money held beyond what is now owed. The invoice's balance and refund-due figures are derived from those records every time rather than stored. An invoice with a payment or credit note cannot be voided; the way to cancel it is a full credit note followed by a refund. Claim tracking and the end-of-day cash count are bookkeeping records; nothing is sent to an insurer or a payment provider. The application adds up the tax rates staff enter and does not decide what tax applies.

## Audit, events and logging

`audit_logs` records actor, organisation, action, resource, outcome, address, user agent, correlation id and, for sensitive changes, field names, never clinical text. `clinical_events` is an outbox of domain events (for example `ENCOUNTER_COMPLETED`) with identifiers only. Logs are JSON, carry the request correlation id and contain no transcript text or vendor error text; tests assert this. The access log records the route template (`/patients/{patient_id}`), never the raw path, so record ids do not appear in it. Prometheus metrics use route templates as labels so no identifier reaches monitoring.

## Scheduled jobs

`python -m app.cli run-job NAME` runs one of `purge-audio`, `pause-stale-recordings` or `purge-refresh-tokens`. Each takes a PostgreSQL advisory lock so overlapping runs skip, writes a row to `job_runs` and exposes its last success time as a metric. A scheduler is not included; use cron or a Kubernetes CronJob (`OPERATIONS.md`).

## Error handling

Errors use a problem-details shape: `type`, `title`, `status`, `detail` and `correlation_id`. Consent failures return 409 `consent_required` with the missing purposes; unsafe prescriptions return 409 `warnings_require_acknowledgement`; rate limits return 429 with `retry_after_seconds`. AI endpoints report an unavailable model as a successful response with `status: FAILED` and a message, so a client never mistakes it for a failed save. FHIR endpoints return OperationOutcome errors.

## Mobile design points

Every API response is parsed with zod, so a server change that breaks a screen fails loudly in one place. Pure logic (dosing, billing totals, tax, EMR layout, worklists, print HTML) lives in `src/domain` with unit tests. PDFs are generated on the phone from HTML so every Indian script renders. The design system (`src/design-system`) provides tokens and components; contrast pairs were computed against WCAG AA for both themes, and `DESIGN_REVIEW.md` records what was and was not reviewed.

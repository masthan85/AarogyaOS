# Security

## Authentication
Argon2id password hashing. Short-lived JWT access tokens (15 min) carrying user id,
organisation id, and session id. Opaque refresh tokens, stored hashed, rotated on every
use; reuse of a rotated token revokes the whole family. Accounts have `mfa_enabled`
and `mfa_secret` fields reserved for TOTP (MFA-ready). OIDC federation is an ADR-level
future option; the token interface is kept IdP-agnostic. Login rate limiting and
lockout after repeated failures.

## Authorisation
RBAC with permissions as strings (`patient:read`). Role-permission mapping lives
in the database and is seeded. Every endpoint declares its permission; checks run on
the server. Facility scoping applies where a role is facility-bound. ABAC (e.g.
care-team relationship, break-glass) is a planned extension point
(`authorize(user, action, resource)`).

## Tenant isolation
Every tenant row has `organisation_id`; services receive a tenant-bound context;
queries filter by it. Postgres RLS on tenant tables is added as defence in depth.
Cross-tenant tests are mandatory in CI.

## Data protection
TLS in transit; encryption at rest (managed volumes + object-store SSE; field-level
encryption for ABHA numbers and similar identifiers, planned Phase 2). Secrets via
environment/secret manager only; `.env` never committed; startup refuses
production mode with default secrets.

## Mobile
Tokens in Keychain/Keystore via secure store; no PHI in logs, analytics or push
payloads; optional screenshot blocking on sensitive screens by org policy; biometric
unlock gate; no clipboard of PHI; encrypted local drafts.

## Patient data (Phase 2)
- Least privilege: administrators have **no** patient permissions. Lab, pharmacy and billing can search
  (name, age, sex, masked mobile) but cannot open records. Reception has no clinical timeline.
- ABHA numbers and other identifiers are AES-256-GCM encrypted with a context-bound AAD; lookups use an
  HMAC blind index with a separately derived key. Unmasking requires `patient:identifier` and is audited.
  `AAROGYA_FIELD_ENCRYPTION_KEY` is required in production; rotation is supported by the `v1:` ciphertext
  prefix but a re-encryption job is not built yet.
- Every patient open, search (result count only, never the query), timeline view and identifier reveal is audited.
  Audit rows and outbox events hold ids and field *names*, never demographics. Previous demographic values live in
  `patient_revisions`.
- Known gaps: no rate limiting on search (an authorised user can enumerate by 3-letter prefixes, 20 at a time —
  mitigated only by audit; add rate limits and anomaly alerts in Phase 7); any user with `patient:read` can open
  any patient in their organisation (care-team ABAC and break-glass are Phase 3+); mobile list caches are
  short-lived (60 s) and cleared on sign-out but are not encrypted on disk because they are memory-only.

## Clinical record (Phase 3)
- The record is append-only and enforced in the database (triggers), so a bug or a compromised application account
  cannot rewrite history. Database superusers can still bypass triggers: restrict, monitor and never use them for
  the application.
- Clinical writes are limited to the encounter's own doctor (notes, diagnoses, prescriptions, orders, follow-ups);
  nurses record triage-level information; lab and radiology technicians see only their own department's placed orders.
- Audit rows and events contain ids, types and flags, never clinical text. Tests assert this.
- Known gaps: staff are not yet scoped to facilities or care teams (any clinician in the organisation can open any
  patient; all access is audited); no break-glass flow; no idempotency keys on clinical writes.

## Consent, recording and audio (Phase 4)
- Eight separate consent purposes; no purpose implies another. History is append-only (database triggers) and
  each consent records who captured it, the wording version shown, the language, and any representative.
- WebSocket: bearer token in the first message only (not the URL), 5 s auth deadline, 64 KiB frame limit, even
  frame length, session time limit, one connection per session, consent and session status re-checked on a timer.
- Transcripts are readable only by the person who recorded and, for clinical sessions, the encounter's doctor.
  Opening a transcript is audited; polling is not (to avoid log flooding).
- Logs, audit rows and events never contain transcript text or vendor error text (tested).
- Audio at rest is encrypted per chunk; there is no download endpoint.
- Third-party processing: sending audio to a speech vendor is a disclosure of health data. Before any real
  provider is enabled: signed DPA, data-residency decision, retention/training opt-out in writing, security review.
- Regulatory notes (from law-firm summaries of the DPDP Rules 2025, notified November 2025, most duties
  phasing in to about May 2027; **verify against the gazette with counsel**): verifiable parental consent for
  children's data, with a carve-out for health professionals that must be checked; notice and consent duties
  still apply to health data; breach reporting; consent-manager provisions from November 2026.

## Runtime hardening (Phase 7)
Security headers on every response; `Cache-Control: no-store` and a restrictive CSP on `/api/`; HSTS in production;
request-size cap; production config refuses default secrets, default DB password and wildcard CORS; metrics labels carry
no identifiers; job failures record only the exception class; backups refuse to be written unencrypted.
Known gaps: no login rate limiting beyond account lockout, no WAF/TLS in this repo, no field-key rotation, access logs
contain record ids in paths.

## Clinical AI (Phase 5)
- Model output is untrusted input: strict parsing, schema validation, exact-quote grounding, whitelisted attributes.
  Transcript text is passed as data inside delimiters, never as instructions; prompt-injection text in a
  conversation cannot create a candidate that is not grounded in a quote, and cannot create a safety suggestion.
- Purpose limitation: reception sessions cannot produce clinical facts; AI needs its own consent, re-checked on every run.
- Minimum necessary: the model receives the transcript window and, for suggestions, coded record items and approved
  passages. The record's names, phone numbers, addresses and identifiers are not sent; what people say aloud in the conversation (which may include a name) is, so this is a reason for the separate AI_PROCESSING consent and the vendor agreement.
- No clinical text in logs, events or usage rows. Candidate and suggestion rows are PHI and live behind RLS.
- Separation of duties: reference documents are approved by someone other than their creator.
- Vendor use of data: no real LLM adapter exists. Before one is added: data-processing agreement, no training on
  our data, residency decision, retention terms.

## Audit
Append-only `audit_logs`: actor, organisation, action, resource, outcome, ip,
user agent, correlation id, before/after for sensitive changes, AI involvement.

## Open items needing specialist review
DPDP Act 2023 compliance and rules, data residency, pentest, threat model for audio
gateway, key management, DPA with each AI provider.

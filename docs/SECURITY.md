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

## Audit
Append-only `audit_logs`: actor, organisation, action, resource, outcome, ip,
user agent, correlation id, before/after for sensitive changes, AI involvement.

## Open items needing specialist review
DPDP Act 2023 compliance and rules, data residency, pentest, threat model for audio
gateway, key management, DPA with each AI provider.

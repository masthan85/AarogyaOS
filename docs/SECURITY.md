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

## Audit
Append-only `audit_logs`: actor, organisation, action, resource, outcome, ip,
user agent, correlation id, before/after for sensitive changes, AI involvement.

## Open items needing specialist review
DPDP Act 2023 compliance and rules, data residency, pentest, threat model for audio
gateway, key management, DPA with each AI provider.

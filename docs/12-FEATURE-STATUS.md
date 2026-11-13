# Feature status

This is the evidence-based inventory of what exists. Status words are used strictly:

- **Working (tested)**: implemented and covered by automated tests that pass in this repository.
- **Working (checked by hand)**: run and observed, not covered by automated tests.
- **Built, not run live**: the code exists and passes tests against fakes, but has never run against the real external service or device.
- **Partial**: some of the intended behaviour exists; the gap is stated.
- **Not built**: no code.

"Tested" means backend tests in `services/api/tests` unless a mobile test is named. All backend and mobile tests passed on the last run (see `10-TESTING-GUIDE.md`). Mobile screens are compile-checked and linted by the type checker; unless stated, nobody has seen them on a physical device.

## Platform

| Feature | Status | Evidence and limits |
|---|---|---|
| Login, refresh-token rotation with reuse detection, lockout, Argon2id | Working (tested) | `test_auth.py` |
| Two-step sign-in (authenticator app, recovery codes, replay guard, admin reset) | Working (tested) | `test_mfa.py`, including the RFC 6238 reference vector. Optional per user; not enforced by role; no QR code; mobile screens compile-checked and unit-tested for logic only |
| Role-based permissions on every endpoint | Working (tested) | `test_permissions.py`, role matrices in most feature tests |
| Tenant isolation with forced row-level security | Working (tested) | `test_tenant_isolation.py`, per-feature cross-tenant tests. Depends on a non-superuser database role |
| Field encryption of identifiers, key rotation | Working (tested) | `test_crypto_and_normalise.py`, `test_key_rotation.py`. Tested on a development database only |
| Audit log and event outbox without clinical text | Working (tested) | `test_audit_and_misc.py` and assertions in feature tests |
| Health, readiness, metrics, security headers, size cap | Working (tested) | `test_operations.py` |
| Contract check between the app's schemas and the API's response fields | Working (tested) | `contract.test.ts` and `test_contract.py` (field names only) |
| Scheduled jobs with locking and ledger | Working (tested) | `test_operations.py`. No scheduler is shipped |
| Rate limiting (login, search) | Partial | `test_ratelimit.py`. Per worker process only |
| Encrypted backup and restore drill | Working (checked by hand) | Run against a development database; a tampered backup was rejected. Not automated |
| Load test | Working (checked by hand) | One run: about 147 requests per second, no errors, on one machine, excluding login, AI and audio |
| Docker image and compose stack | Built, not run live | No Docker daemon was available |
| Repeated payment, credit note and refund requests recorded once (`Idempotency-Key`) | Working (tested) | `test_release_gates.py`, including four identical requests racing. Not yet on draft invoices, prescriptions or walk-ins |
| Provider approval list checked at start-up in production, fallback included | Working (tested) | `test_release_gates.py`. Records a decision; does not prove an agreement exists |
| One live instance (advisory lock, `standby` readiness, audio refused elsewhere) | Working (tested) | `test_release_gates.py`. Not exercised on a real platform |
| Recordings marked interrupted after a restart | Working (tested) | `test_release_gates.py` |
| Monthly speech and AI allowances per organisation | Working (tested) | `test_release_gates.py`. No outbound alert: the usage screen or a monitor must be watched |
| Connection banner in the app; nothing queued offline | Built, partly checked | Client behaviour in `client.test.ts`. In a browser the banner appeared when the server was stopped and cleared when it returned. Not exercised on a device |

## Front desk

| Feature | Status | Evidence and limits |
|---|---|---|
| Patient registration, duplicate detection, minimal-field search | Working (tested) | `test_patients.py` |
| Appointments, slots, walk-ins, check-in, queue, working hours | Working (tested) | `test_scheduling.py`. Admin screens for practitioners and hours exist in the app |
| Patient timeline | Working (tested) | `test_patients.py` |
| Duplicate merge | Not built | Needs clinical governance decisions; touches immutable rows |
| Patient photo | Not built | Needs object store |
| Push reminders | Not built | |

## Clinical record

| Feature | Status | Evidence and limits |
|---|---|---|
| Encounters (triage then consultation), handover between doctors | Working (tested) | `test_clinical_workflow.py`, `test_handover.py` |
| Vitals with unit conversion, plausibility limits, flags | Working (tested) | `test_clinical_workflow.py`. Reference ranges need clinical sign-off, including paediatric |
| Notes, diagnoses with certainty, allergies, medicine history | Working (tested) | `test_clinical_workflow.py` |
| Provenance, verification workflow, append-only corrections | Working (tested) | `test_clinical_workflow.py`, direct-SQL immutability checks |
| Investigations: draft, place, structured results, review, doctor cover | Working (tested) | `test_orders_and_followups.py`, `test_cover.py` |
| Prescriptions: draft, edit, safety check, acknowledge, sign, void | Working (tested) | `test_prescriptions.py`. Safety check is allergy-by-name only |
| Drug interactions, contraindications, dose checks | Not built | Needs a licensed drug knowledge source |
| Prescription seal (tamper evidence) | Working (tested) | `test_retention.py`. Not a legal digital signature |
| Follow-ups, with scheduling from "come back after 5 days" | Working (tested) | `test_orders_and_followups.py`, `test_followup_when.py`, `test_circumstance_and_followup.py` |
| Procedures, vaccines, referrals | Working (tested) | `test_history.py`. No vaccine schedule or reminders; no referral letter sending |
| Pharmacy dispensing record | Working (tested) | `test_dispensing.py`. No stock, brand or batch tracking |
| Coded diagnoses and medicines (ICD, SNOMED, LOINC) | Not built | Needs a licensed terminology service. Code fields exist and stay empty |
| Result file upload (PDF, images) | Not built | Needs object store |
| Care-team scoping, break-glass access | Not built | Any clinician in the organisation can open any patient; all access audited |

## Consent and recording

| Feature | Status | Evidence and limits |
|---|---|---|
| Eight consent purposes, versioned wording, guardians, withdrawal | Working (tested) | `test_consent.py`. Wording is unreviewed templates |
| Recording sessions, explicit start and stop, consent re-checks | Working (tested) | `test_interactions.py` |
| Audio WebSocket gateway, limits, retention, purge | Working (tested) | `test_gateway.py`. Live partial transcripts are in process memory |
| Speech provider layer with fallback, development provider | Working (tested) | `test_speech_package.py` |
| Sarvam streaming speech-to-text | Built, not run live (partly) | `test_sarvam.py` against a fake server. One live run with a short English clip connected and returned segments. Accuracy on Indian languages, code-mixed speech and drug names is unmeasured |
| Microphone capture on a device | Built, not run live | Unit-tested against fakes (`gateway.test.ts`, `capture.test.ts`). Never on a device: see `DEVICE_TEST_PLAN.md` |
| Speaker assignment, transcript corrections | Working (tested) | `test_interactions.py`, `test_transcript_corrections.py` |
| Legal holds on audio deletion | Working (tested) | `test_retention.py`, `test_gateway.py` |
| Object-store audio retention | Not built | Local encrypted directory only |
| Records retention schedule and erasure workflow | Not built | Needs legal advice; nothing is auto-deleted |

## Clinical AI

| Feature | Status | Evidence and limits |
|---|---|---|
| Extraction with guardrails and review queue | Working (tested) | `test_ai_extraction.py`, `test_ai_guardrails.py` against the development model |
| Accept, edit, reject into facts with provenance | Working (tested) | `test_ai_extraction.py`. Draft EMR screen compile-checked and viewed in a browser build |
| Rule-based and model suggestions with citations | Working (tested) | `test_ai_suggestions.py` |
| Reference knowledge library with two-person approval | Working (tested) | `test_ai_suggestions.py`. Search ranks in Python unless pgvector is installed; embeddings are a development stand-in |
| Ask the chart, with keyword fallback | Working (tested) | `test_templates_letters_qa.py` |
| Anthropic model adapter | Built, not run live | `test_anthropic_llm.py` with a stub. Needs a data agreement and residency decision |
| Sarvam chat model, translation, read-aloud | Working (checked by hand) | One live run each (`SARVAM.md`). Audio not yet listened to; Hindi not read by a clinician |
| Self-hosted OpenAI-compatible model adapter | Built, not run live | `test_self_hosted_llm.py` |
| Evaluation harness | Partial | Exists, with tiny synthetic gold sets. No clinician-labelled set |
| Accuracy measured on real clinical audio | Not built | |

## Documents, billing and interoperability

| Feature | Status | Evidence and limits |
|---|---|---|
| Note templates (built-in, organisation, neurosurgery) | Working (tested) | `test_templates_letters_qa.py`. The neurosurgery layout is unreviewed by a neurosurgeon |
| Visit summaries and referral letters, code-built, approved and frozen | Working (tested) | `test_templates_letters_qa.py` |
| PDF share and print | Built, not run live | Generated on the phone; HTML builders unit-tested (`print.test.ts`); never run on a device |
| Billing: invoices, payments, tax lines, numbering and freeze | Working (tested) | `test_billing.py`, `test_billing_extras.py`, `billing.test.ts`. Billing flow also driven through the real API in a browser build |
| Credit notes, refunds, price list, claim tracking, day close | Working (tested) | `test_billing_extras.py`. New screens compile-checked, not viewed rendered |
| Tax rules, CGST and SGST split, tax-invoice wording | Not built | Staff enter rates; needs accountant sign-off |
| Payment gateway; sending claims to insurers | Not built | Needs provider accounts |
| FHIR R4 visit document export | Working (tested) | `test_fhir.py`, validated with `fhir.resources` R4B. Not ABDM profile conformant |
| ABDM (ABHA, consent manager, HIP and HIU) | Not built | Paused; needs the implementation guide version and sandbox credentials |
| Sending letters or records to other providers | Not built | |

## Mobile app

| Feature | Status | Evidence and limits |
|---|---|---|
| Role-aware home, queue, patients, appointments, triage, consultation tabs | Built, partly checked by hand | Rendered in a browser build against a demo clinic during the design review. Not on a device |
| Administration screens (policy, staff, templates, knowledge, usage, audit) | Built, compile-checked | Not viewed on a device |
| Worklists (results, follow-ups, lab orders), pharmacy, cover | Built, compile-checked | Logic tests in `worklists.test.ts` |
| Billing screens | Built, partly checked by hand | Invoice flow checked in a browser build; later screens (price list, end of day, adjustments, claims) not viewed |
| Procedures tab, seal check, legal hold card | Built, compile-checked | Not viewed rendered |
| Biometric unlock, secure token store | Built, not run live | Needs a device |
| Offline behaviour | By design none for clinical writes | Failed saves say nothing was saved |
| Patient-facing app or portal | Not built | |

## Differences from the original vision

The original baseline imagined shared TypeScript packages (`packages/shared-types`, `api-client`, `design-system`), a separate `services/clinical-ai` service, Redis and S3-compatible storage, idempotency keys, cursor pagination, optimistic concurrency everywhere, an encrypted offline outbox on the phone, a three-pane tablet consultation layout, and care-team and break-glass access. The build deliberately stayed simpler: one API package with `app/ai` and `app/speech` inside it, one app package, and the mobile design system inside the app. Redis is declared in Compose but unused, audio is stored on local disk, lists are capped rather than paginated, and offline writes were rejected as a safety choice. The tablet-width layout keeps the patient context beside the work but is not the three-pane design. Billing, procedures, vaccines, referrals, seals and legal holds were added after the baseline and are not part of it.

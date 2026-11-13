# API documentation

The API is a REST service over JSON with one WebSocket. Base path `/api/v1`. The authoritative, always-current reference is the OpenAPI document FastAPI generates (`/docs` and `/openapi.json`; both are disabled when `AAROGYA_ENVIRONMENT=production`). This file explains the conventions and lists each endpoint with the permission it needs. The endpoint index at the end was extracted from the router source files and covers about 160 routes.

## Conventions

Authentication is a bearer access token from `POST /auth/login` (body: `organisation_slug`, `email`, `password`, and `mfa_code` once two-step sign-in is on), renewed with `POST /auth/refresh` (the refresh token rotates on every use). `GET /auth/me` returns the user, roles and permissions, which the mobile app uses to decide which screens to show. Every endpoint except the auth, language-catalogue and health routes needs a valid token, and nearly all declare a permission that the server checks.

Errors follow a problem-details shape: `{type, title, status, detail, correlation_id}`. Every response carries `X-Request-ID`; send one to correlate client and server logs. FHIR endpoints return OperationOutcome errors instead. Identifiers are UUIDs. Money is always an integer number of paise. Lists are capped rather than paginated; there are no idempotency keys, and optimistic concurrency (`expected_version`, 409 when stale) exists only for patient updates.

Operational endpoints outside the prefix: `GET /health` (liveness), `GET /ready` (database reachable and migrated; 503 `migrations_pending` otherwise) and `GET /metrics` (Prometheus text, bearer token in production).

## Identity, organisation and audit
| Method & path | Permission |
|---|---|
| `POST /auth/login`, `/auth/refresh`, `/auth/logout` | public |
| `GET /auth/me` | authenticated |
| `POST/GET /organisations` | `platform:organisations` |
| `GET /organisations/current` | `org:read` |
| `GET/POST /facilities`, `GET/PATCH /facilities/{id}` | `facility:read` / `facility:manage` |
| `GET/POST /departments` | `department:read` / `department:manage` |
| `GET/POST /users`, `GET /users/{id}`, `PUT /users/{id}/roles`, `POST /users/{id}/deactivate` | `user:read` / `user:manage` |
| `GET /roles` | `role:read` |
| `GET /audit-logs` | `audit:read` |

## Patients and scheduling
| Method & path | Permission |
|---|---|
| `POST /patients` (409 `possible_duplicate` with candidates unless `confirm_not_duplicate`) | `patient:create` |
| `GET /patients/search?name=&mobile=&mrn=` (minimal fields, max 20, name needs 3+ letters) | `patient:search` |
| `GET /patients/{id}` | `patient:read` |
| `PATCH /patients/{id}` (requires `expected_version`; 409 if stale) | `patient:update` |
| `POST /patients/{id}/identifiers` | `patient:update` |
| `POST /patients/{id}/identifiers/{iid}/reveal` (audited) | `patient:identifier` |
| `GET /patients/{id}/timeline` | `patient:timeline` |
| `POST /practitioners`, `PUT /practitioners/{id}/working-hours` | `practitioner:manage` |
| `GET /practitioners`, `GET /practitioners/{id}/slots?on=YYYY-MM-DD` | `practitioner:read` / `appointment:read` |
| `POST /appointments`, `/{id}/reschedule`, `/{id}/cancel`, `/{id}/confirm`, `/{id}/no-show` | `appointment:manage` |
| `GET /appointments?on=&facility_id=&practitioner_id=&patient_id=&status=` | `appointment:read` |
| `POST /appointments/{id}/check-in`, `POST /walk-ins` | `queue:manage` |
| `POST /appointments/{id}/start-consultation`, `/{id}/complete` | `queue:call` |
| `GET /queue?facility_id=&practitioner_id=` | `queue:read` |

Appointment states: BOOKED → CONFIRMED → (ARRIVED/CHECKED_IN) → WAITING → IN_CONSULTATION → COMPLETED, with
CANCELLED and NO_SHOW as exits. Check-in currently moves straight to WAITING; ARRIVED/CHECKED_IN are accepted
by the state machine but unused until consent/triage steps exist. Transitions outside the table return 409.

## Clinical record
| Area | Endpoints | Permission |
|---|---|---|
| Encounter | `POST /encounters/triage` (idempotent), `PUT /encounters/{id}/triage-category` | `encounter:triage` |
| | `POST /encounters/consultation` (takes over the triage encounter; moves the appointment), `POST /encounters/{id}/complete` | `encounter:consult` |
| | `GET /encounters/{id}`, `GET /patients/{id}/encounters` | `encounter:read` |
| Vitals | `POST /encounters/{id}/vitals` (°C/°F, plausibility checks), `PUT /observations/{id}` (correction) | `vitals:record` |
| Notes | `POST /encounters/{id}/notes`, `PUT /notes/{id}` (triage types: `note:triage`; others: `note:clinical` and owning doctor) | `encounter:read` + per type |
| Diagnoses | `POST /encounters/{id}/conditions`, `PUT /conditions/{id}` | `condition:record` (`condition:confirm` to confirm) |
| Allergies / medicines | `POST /encounters/{id}/allergies`, `.../medications`, `PUT /allergies/{id}`, `PUT /medications/{id}` | `allergy:record`, `medication:record` |
| Verification | `POST /clinical/{kind}/{id}/verify` (`confirm`/`reject` with reason; diagnoses need `condition:confirm`) | `fact:verify` |
| State | `GET /patients/{id}/clinical-state`, `GET /patients/{id}/vitals?code=` | `patient:clinical` |
| Prescriptions | `POST /encounters/{id}/prescriptions`, `PUT /prescriptions/{id}`, `POST .../safety-check`, `POST .../void` | `prescription:write` |
| | `POST /prescriptions/{id}/sign` (409 `warnings_require_acknowledgement` lists warnings to acknowledge) | `prescription:sign` |
| | `GET /prescriptions/{id}`, `GET /patients/{id}/prescriptions` (non-authors see signed only) | `prescription:read` |
| Investigations | `POST /encounters/{id}/orders`, `POST /orders/{id}/place`, `POST /orders/{id}/cancel` | `order:write` |
| | `GET /orders` (drafts hidden from non-authors; technicians see their department only) | `order:read` |
| Results | `POST /orders/{id}/results` (interpreted against the lab-supplied range) | `result:enter` |
| | `GET /results/awaiting-review`, `POST /results/{id}/review` | `result:review` |
| Follow-up | `POST /encounters/{id}/follow-ups`, `POST /follow-ups/{id}/status` | `followup:write` |
| | `GET /follow-ups` | `followup:read` |

## Consent, speech, AI, documents and FHIR
| Area | Endpoints | Permission |
|---|---|---|
| Wording | `POST /consent-policies`, `POST /consent-policies/install-templates` (unreviewed templates) | `consent:manage` |
| | `GET /consent-policies` | `consent:policy` |
| Consent | `GET /patients/{id}/consents` (status per purpose + history), `POST /patients/{id}/consents`, `POST /consents/{id}/withdraw` | `consent:read` / `capture` / `withdraw` |
| Policy | `GET/PUT /organisations/current/policy` | `org:read` / `org:manage` |
| Languages | `GET /languages` | any signed-in user |
| Sessions | `POST /interactions`, `/{id}/start`, `/pause`, `/resume`, `/stop`, `GET /interactions/{id}` | purpose permission; session owner |
| Transcript | `GET /interactions/{id}/transcript?after_seq=`, `GET /interactions/{id}/events` (SSE), `PUT /interactions/{id}/speakers/{speaker_id}`, `GET /patients/{id}/interactions` | `transcript:read` / `speaker:assign` |
| Audio | `WS /interactions/{id}/audio` (see `SPEECH_ARCHITECTURE.md`) | session owner |
| Usage | `GET /usage/speech` | `usage:read` |

| AI analysis | `POST /interactions/{id}/ai/analyse`, `GET /interactions/{id}/ai/candidates`, `GET /encounters/{id}/ai/review` (candidates + suggestions + switches) | `ai:analyse` / `ai:review`; session owner or encounter doctor |
| Candidate review | `POST /ai/candidates/{id}/review` `{action: accept\|edit\|reject, edited_text?, mode?: note\|prescription_draft}` | `ai:review`; doctor-only kinds need `note:clinical` and encounter ownership |
| Suggestions | `POST/GET /encounters/{id}/ai/suggestions`, `POST /ai/suggestions/{id}/action` `{action: accept\|edit\|reject\|dismiss}` | `ai:suggestions`; encounter's doctor only |
| Reference knowledge | `GET/POST /knowledge/documents`, `POST /knowledge/documents/{id}/approve`, `/retire` | `knowledge:read` / `knowledge:manage` (approver must differ from creator) |
| Patient summary | `POST/GET /encounters/{id}/summaries`, `PUT /summaries/{id}`, `POST /summaries/{id}/approve` | `summary:write` / `summary:read`; encounter's doctor |
| AI usage | `GET /usage/ai` | `usage:read` |
| This month's use against the organisation's allowances | `GET /usage/limits` | `usage:read` |

| FHIR export | `GET /fhir/metadata`, `/fhir/Patient/{id}`, `/fhir/Encounter/{id}`, `/fhir/Encounter/{id}/$export-document` (see `INTEROPERABILITY.md`; `application/fhir+json`, errors as OperationOutcome) | `fhir:export`; encounter's doctor |

| Note templates | `GET /note-templates` (built-in + organisation, active only), `GET /note-templates/all`, `POST /note-templates`, `PUT /note-templates/{id}` | read: `note:clinical`; write: `org:manage` |
| Referral letters | `POST /encounters/{id}/letters` (draft); listing, `PUT /summaries/{id}` (edit) and `POST /summaries/{id}/approve` are shared with visit summaries, which carry a `kind` | `summary:write`; encounter's doctor |
| Chart question | `POST /patients/{id}/ai/ask` `{question}` -> cited answer (when AI is on and consented) plus matching entries (always) | `ai:suggestions` + `patient:clinical` |

| Read aloud | `POST /summaries/{id}/speech` -> `audio/wav` of an approved summary or letter (not stored) | `summary:read`; encounter's doctor; AI switch + patient consent; `503` if no voice service is connected |

Errors of note: `409 consent_required` carries `missing: [...]`; `503` when the speech provider is unavailable. AI endpoints report an unavailable model as `200 {status: FAILED, message}` rather than an error, so a client never treats it as a failed save.

The earlier appointment-level `start-consultation` and `complete` endpoints and the `queue:call` permission were removed; the encounter workflow above replaces them.

## Cover (migration 0008)

| Method and path | Permission | Notes |
|---|---|---|
| `GET /cover/colleagues` | `result:review` | Other active doctors in the organisation |
| `GET /cover` | `result:review` | Arrangements I made or that name me (ended ones for 30 days) |
| `POST /cover` | `result:review` | `{to_user_id, starts_on, ends_on}`; at most 31 days, not more than a year ahead |
| `POST /cover/{id}/end` | `result:review` | Either side may end it |

While an arrangement is active, `GET /results/awaiting-review` for the covering doctor also returns the other doctor's results, each marked `covering_for`. Reviews are audited with `on_behalf_of`.

## Transcript corrections (migration 0009)

| Method and path | Permission | Notes |
|---|---|---|
| `PUT /interactions/{id}/segments/{segment_id}/correction` | `transcript:correct` (doctor, nurse) | `{"text": "..."}` records a correction; `{"text": null}` goes back to what was heard. Only the person who made the recording can reach it. Returns the segment with `corrected_text` |

`GET /interactions/{id}/transcript` returns `raw_text` (never changes) and `corrected_text` (null unless corrected). The assistant reads, and quotes from, the corrected text when it analyses later lines.

## Rate limits

`POST /auth/login`: 60 per minute per client address. `GET /patients/search`: 60 per minute per user. Over the limit: `429` with `retry_after_seconds`. Per worker process (see `16-SECURITY.md`).

## Handover

`POST /encounters/{id}/handover` (`encounter:consult`, current doctor only) with `{"to_practitioner_id": "..."}` passes a consultation that is under way to another active doctor at the same facility. Refused with 409 while prescription or order drafts exist or a recording is open; 404 for an unknown or same doctor. The appointment and queue entry follow. Audited as `ENCOUNTER_HANDED_OVER`.

## Dispensing (migration 0010)

| Method and path | Permission | Notes |
|---|---|---|
| `POST /prescriptions/{id}/dispensing` | `prescription:dispense` (pharmacist) | `{status: DISPENSED \| PARTIALLY_DISPENSED \| NOT_DISPENSED, note?}`. Signed prescriptions only; 409 once fully dispensed or if voided |
| `GET /patients/{id}/dispensings` | `prescription:read` | Newest first |

Append-only (database trigger). Records the decision and who made it; there is no stock, brand or batch tracking and no interaction check.

## Billing (migrations 0011 and 0013)

| Method and path | Permission | Notes |
|---|---|---|
| `GET /billing/to-bill` | `billing:write` | Visits finished in the last 7 days with no invoice (a void one does not count): patient name, MRN, doctor, time. Nothing clinical |
| `GET /invoices` | `billing:read` | `?status=DRAFT\|ISSUED\|VOID`, `?patient_id=`, `?unpaid=true` (issued with a balance) |
| `POST /invoices` | `billing:write` | `{patient_id, encounter_id?}`; one live invoice per visit |
| `GET /invoices/{id}` | `billing:read` | Lines, payments, `total_paise`, `paid_paise`, `balance_paise` |
| `PUT /invoices/{id}/lines` | `billing:write` | Replaces the charges of a draft (up to 30; whole paise; quantity 1 to 999) |
| `POST /invoices/{id}/issue` | `billing:write` | Needs a charge and a total above zero; assigns `INV-000001` style numbers per organisation and freezes the invoice |
| `POST /invoices/{id}/payments` | `billing:write` | `{amount_paise, method: CASH\|UPI\|CARD\|INSURER\|OTHER, reference?}`; never more than the balance |
| `POST /invoices/{id}/void` | `billing:write` | Discards a draft (returns `null`), or voids an issued invoice that has no payments and no credit notes. To cancel a paid invoice, issue a full credit note and refund (below) |

Roles: billing staff and reception read and write; credit notes, refunds and claims need `billing:adjust` (billing staff and administrators); the price list and GSTIN need `billing:manage` (billing staff and administrators); administrators otherwise read; doctors, nurses, lab and pharmacy have no billing access. Billing staff see names, MRNs and amounts, never the clinical record.

## Procedures, immunisations and referrals (migration 0012)
All three are ordinary clinical facts: provenance, verification state, and corrections that add a new version.
- `GET /patients/{id}/history` — current procedures, vaccines and referrals (`patient:clinical`).
- `POST /encounters/{id}/procedures`, `PUT /procedures/{id}` — doctors (`procedure:record`). Date performed cannot be in the future.
- `POST /encounters/{id}/immunisations`, `PUT /immunisations/{id}` — nurses and doctors (`immunisation:record`). A nurse's entry stays unverified until a doctor confirms it. The next dose must be due after this one.
- `POST /encounters/{id}/referrals`, `PUT /referrals/{id}` — doctors (`referral:write`). Status: requested, accepted, completed, declined, cancelled. A closed referral cannot be changed; start a new one.
- Confirm or reject with the existing `POST /clinical/{procedures|immunisations|referrals}/{id}/verify`.

### Tax, credit notes, refunds, price list, claims and day close
- Lines take `tax_rate_bp` (1800 = 18%, 0 to 2800). Tax is worked out per line, rounded half up, and the invoice stores `tax_paise`, `total_paise` (tax included) and the seller's GSTIN as it was when issued. Payment methods now include `INSURER`.
- `POST /invoices/{id}/credit-notes` `{amount_paise, reason}` — numbered CN-000001; cannot exceed what the invoice is still worth. `billing:adjust`.
- `POST /invoices/{id}/refunds` `{amount_paise, method, reason}` — only up to `refund_due_paise` (paid minus refunded minus what is owed). `billing:adjust`.
- An invoice with a payment or credit note cannot be voided: credit it in full and refund what was paid.
- Invoice fields: `credited_paise`, `net_paise`, `refunded_paise`, `balance_paise` (still owed), `refund_due_paise`, `credit_notes`, `refunds`.
- `GET/PUT /billing/settings` (GSTIN shape-checked, not verified against the GST portal; `billing:manage` to change).
- `GET/POST /billing/prices`, `PUT /billing/prices/{id}` — price list; names unique ignoring case; hiding a service keeps old invoices intact. `billing:manage`.
- `GET /billing/day?on=YYYY-MM-DD` — received, refunded and net by method for an India-time day; `POST /billing/day/close` `{business_date, counted_cash_paise, note}` records expected vs counted cash once per day (`billing:write`).
- `GET/POST /invoices/{id}/claims`, `PUT /claims/{id}` — claim tracking only (submitted, approved, part approved, rejected, settled). Nothing is sent to an insurer. `billing:adjust`.

## Seals and legal holds (migration 0014)
- `GET /prescriptions/{id}/integrity` — `{sealed, intact, message}`. When a doctor signs, the server stores a keyed hash (HMAC-SHA256, keyed from the field encryption key) over who signed, when, and every line. The check recomputes it, so a change made directly in the database shows as "does not match". This is tamper evidence, **not** a legal digital signature: there is no certificate or eSign. Prescriptions signed before this release have no seal and report "cannot be checked". Rotating the key keeps old seals valid only while the previous key stays listed in `AAROGYA_FIELD_ENCRYPTION_PREVIOUS_KEYS`. `prescription:read`.
- `POST /patients/{id}/legal-holds` `{reason}`, `POST /legal-holds/{id}/release` `{reason}`, `GET /legal-holds?patient_id=&all=` — administrators only (`legalhold:manage` / `legalhold:read`). While a hold is active the audio purge job skips that patient, even for expired retention or a withdrawn consent; releasing it lets the normal rules apply again. A hold can be released once and never edited or deleted. Both actions are audited with the reason.
- FHIR document export now includes `Procedure`, `Immunization` and referral `ServiceRequest` resources (base R4, validated in tests) with their own Composition sections.

## Endpoint index

Generated from the router files; the permission column shows the permission declared in the endpoint's signature. A dash means access is decided inside the service (for example, a recording session belongs to the person who started it) or the route is public. The path prefix `/api/v1` is omitted.


### Clinical AI and reference knowledge

| Method | Path | Permission |
|---|---|---|
| POST | `/interactions/{interaction_id}/ai/analyse` | ai:analyse |
| GET | `/interactions/{interaction_id}/ai/candidates` | ai:review |
| GET | `/encounters/{encounter_id}/ai/review` | ai:review |
| POST | `/ai/candidates/{candidate_id}/review` | ai:review |
| POST | `/encounters/{encounter_id}/ai/suggestions` | ai:suggestions |
| GET | `/encounters/{encounter_id}/ai/suggestions` | ai:suggestions |
| POST | `/ai/suggestions/{suggestion_id}/action` | ai:suggestions |
| GET | `/knowledge/documents` | knowledge:read |
| POST | `/knowledge/documents` | knowledge:manage |
| POST | `/knowledge/documents/{doc_id}/approve` | knowledge:manage |
| POST | `/knowledge/documents/{doc_id}/retire` | knowledge:manage |
| GET | `/usage/ai` | usage:read |
| POST | `/patients/{patient_id}/ai/ask` | ai:suggestions, patient:clinical |

### Audit

| Method | Path | Permission |
|---|---|---|
| GET | `/audit-logs` | audit:read |

### Billing

| Method | Path | Permission |
|---|---|---|
| GET | `/billing/to-bill` | billing:write |
| GET | `/invoices` | billing:read |
| POST | `/invoices` | billing:write |
| GET | `/invoices/{invoice_id}` | billing:read |
| PUT | `/invoices/{invoice_id}/lines` | billing:write |
| POST | `/invoices/{invoice_id}/issue` | billing:write |
| POST | `/invoices/{invoice_id}/payments` | billing:write |
| POST | `/invoices/{invoice_id}/void` | billing:write |
| POST | `/invoices/{invoice_id}/credit-notes` | billing:adjust |
| POST | `/invoices/{invoice_id}/refunds` | billing:adjust |
| GET | `/invoices/{invoice_id}/claims` | billing:read |
| POST | `/invoices/{invoice_id}/claims` | billing:adjust |
| PUT | `/claims/{claim_id}` | billing:adjust |
| GET | `/billing/settings` | billing:read |
| PUT | `/billing/settings` | billing:manage |
| GET | `/billing/prices` | billing:read |
| POST | `/billing/prices` | billing:manage |
| PUT | `/billing/prices/{price_id}` | billing:manage |
| GET | `/billing/day` | billing:write |
| POST | `/billing/day/close` | billing:write |

### Clinical record

| Method | Path | Permission |
|---|---|---|
| GET | `/patients/{patient_id}/history` | patient:clinical |
| POST | `/encounters/{encounter_id}/procedures` | procedure:record |
| PUT | `/procedures/{fact_id}` | procedure:record |
| POST | `/encounters/{encounter_id}/immunisations` | immunisation:record |
| PUT | `/immunisations/{fact_id}` | immunisation:record |
| POST | `/encounters/{encounter_id}/referrals` | referral:write |
| PUT | `/referrals/{fact_id}` | referral:write |
| POST | `/encounters/triage` | encounter:triage |
| POST | `/encounters/consultation` | encounter:consult |
| GET | `/encounters/{encounter_id}` | encounter:read |
| PUT | `/encounters/{encounter_id}/triage-category` | encounter:triage |
| POST | `/encounters/{encounter_id}/complete` | encounter:consult |
| POST | `/encounters/{encounter_id}/handover` | encounter:consult |
| GET | `/patients/{patient_id}/encounters` | encounter:read |
| POST | `/encounters/{encounter_id}/vitals` | vitals:record |
| PUT | `/observations/{observation_id}` | vitals:record |
| GET | `/patients/{patient_id}/vitals` | patient:clinical |
| POST | `/encounters/{encounter_id}/notes` | encounter:read |
| PUT | `/notes/{note_id}` | encounter:read |
| POST | `/encounters/{encounter_id}/conditions` | condition:record |
| PUT | `/conditions/{condition_id}` | condition:record |
| POST | `/encounters/{encounter_id}/allergies` | allergy:record |
| PUT | `/allergies/{allergy_id}` | allergy:record |
| POST | `/encounters/{encounter_id}/medications` | medication:record |
| PUT | `/medications/{medication_id}` | medication:record |
| POST | `/clinical/{kind}/{fact_id}/verify` | fact:verify |
| GET | `/patients/{patient_id}/clinical-state` | patient:clinical |
| POST | `/encounters/{encounter_id}/prescriptions` | prescription:write |
| PUT | `/prescriptions/{rx_id}` | prescription:write |
| GET | `/prescriptions/{rx_id}` | prescription:read |
| POST | `/prescriptions/{rx_id}/safety-check` | prescription:write |
| POST | `/prescriptions/{rx_id}/sign` | prescription:sign |
| POST | `/prescriptions/{rx_id}/void` | prescription:write |
| GET | `/patients/{patient_id}/prescriptions` | prescription:read |
| POST | `/encounters/{encounter_id}/orders` | order:write |
| POST | `/orders/{order_id}/place` | order:write |
| POST | `/orders/{order_id}/cancel` | order:write |
| GET | `/orders` | order:read |
| POST | `/orders/{order_id}/results` | result:enter |
| GET | `/results/awaiting-review` | result:review |
| POST | `/results/{result_id}/review` | result:review |
| GET | `/patients/{patient_id}/results` | patient:clinical |
| POST | `/encounters/{encounter_id}/follow-ups` | followup:write |
| GET | `/follow-ups` | followup:read |
| POST | `/follow-ups/{followup_id}/status` | followup:write |
| GET | `/prescriptions/{rx_id}/integrity` | prescription:read |

### Consent

| Method | Path | Permission |
|---|---|---|
| POST | `/consent-policies` | consent:manage |
| POST | `/consent-policies/install-templates` | consent:manage |
| GET | `/consent-policies` | consent:policy |
| GET | `/patients/{patient_id}/consents` | consent:read |
| POST | `/patients/{patient_id}/consents` | consent:capture |
| POST | `/consents/{consent_id}/withdraw` | consent:withdraw |

### Doctor cover

| Method | Path | Permission |
|---|---|---|
| GET | `/cover/colleagues` | result:review |
| GET | `/cover` | result:review |
| POST | `/cover` | result:review |
| POST | `/cover/{cover_id}/end` | result:review |

### Identity

| Method | Path | Permission |
|---|---|---|
| POST | `/auth/login` | - |
| POST | `/auth/refresh` | - |
| POST | `/auth/logout` | - |
| GET | `/auth/me` | - |
| GET | `/auth/mfa` | - |
| POST | `/auth/mfa/enroll` | - |
| POST | `/auth/mfa/confirm` | - |
| POST | `/auth/mfa/disable` | - |
| GET | `/roles` | role:read |
| GET | `/users` | user:read |
| POST | `/users` | user:manage |
| GET | `/users/{user_id}` | user:read |
| PUT | `/users/{user_id}/roles` | user:manage |
| POST | `/users/{user_id}/deactivate` | user:manage |
| POST | `/users/{user_id}/mfa/reset` | user:manage |

### Recording sessions and transcripts

| Method | Path | Permission |
|---|---|---|
| WEBSOCKET | `/interactions/{interaction_id}/audio` | - |
| POST | `/interactions` | - |
| POST | `/interactions/{interaction_id}/start` | - |
| POST | `/interactions/{interaction_id}/pause` | - |
| POST | `/interactions/{interaction_id}/resume` | - |
| POST | `/interactions/{interaction_id}/stop` | - |
| GET | `/interactions/{interaction_id}` | - |
| GET | `/interactions/{interaction_id}/transcript` | transcript:read |
| PUT | `/interactions/{interaction_id}/segments/{segment_id}/correction` | transcript:correct |
| PUT | `/interactions/{interaction_id}/speakers/{speaker_id}` | speaker:assign |
| GET | `/patients/{patient_id}/interactions` | transcript:read |
| GET | `/usage/speech` | usage:read |
| GET | `/usage/limits` | usage:read |
| GET | `/interactions/{interaction_id}/events` | - |

### FHIR

| Method | Path | Permission |
|---|---|---|
| GET | `/fhir/metadata` | fhir:export |
| GET | `/fhir/Patient/{patient_id}` | fhir:export |
| GET | `/fhir/Encounter/{encounter_id}` | fhir:export |
| GET | `/fhir/Encounter/{encounter_id}/$export-document` | fhir:export |

### Languages

| Method | Path | Permission |
|---|---|---|
| GET | `/languages` | - |
| GET | `/organisations/current/policy` | org:read |
| PUT | `/organisations/current/policy` | org:manage |

### Patients

| Method | Path | Permission |
|---|---|---|
| POST | `/patients` | patient:create |
| GET | `/patients/search` | patient:search |
| GET | `/patients/{patient_id}` | patient:read |
| PATCH | `/patients/{patient_id}` | patient:update |
| POST | `/patients/{patient_id}/identifiers` | patient:update |
| POST | `/patients/{patient_id}/identifiers/{identifier_id}/reveal` | patient:identifier |
| GET | `/patients/{patient_id}/timeline` | patient:timeline |

### Pharmacy

| Method | Path | Permission |
|---|---|---|
| POST | `/prescriptions/{rx_id}/dispensing` | prescription:dispense |
| GET | `/patients/{patient_id}/dispensings` | prescription:read |

### Legal holds

| Method | Path | Permission |
|---|---|---|
| GET | `/legal-holds` | legalhold:read |
| POST | `/patients/{patient_id}/legal-holds` | legalhold:manage |
| POST | `/legal-holds/{hold_id}/release` | legalhold:manage |

### Scheduling

| Method | Path | Permission |
|---|---|---|
| POST | `/practitioners` | practitioner:manage |
| GET | `/practitioners` | practitioner:read |
| PUT | `/practitioners/{practitioner_id}/working-hours` | practitioner:manage |
| GET | `/practitioners/{practitioner_id}/slots` | appointment:read |
| POST | `/appointments` | appointment:manage |
| GET | `/appointments` | appointment:read |
| POST | `/appointments/{appointment_id}/reschedule` | appointment:manage |
| POST | `/appointments/{appointment_id}/cancel` | appointment:manage |
| POST | `/appointments/{appointment_id}/confirm` | appointment:manage |
| POST | `/appointments/{appointment_id}/no-show` | appointment:manage |
| POST | `/appointments/{appointment_id}/check-in` | queue:manage |
| POST | `/walk-ins` | queue:manage |
| GET | `/queue` | queue:read |

### Summaries and letters

| Method | Path | Permission |
|---|---|---|
| POST | `/encounters/{encounter_id}/summaries` | summary:write |
| POST | `/encounters/{encounter_id}/letters` | summary:write |
| GET | `/encounters/{encounter_id}/summaries` | summary:read |
| PUT | `/summaries/{summary_id}` | summary:write |
| POST | `/summaries/{summary_id}/approve` | summary:write |
| POST | `/summaries/{summary_id}/speech` | summary:read |

### Note templates

| Method | Path | Permission |
|---|---|---|
| GET | `/note-templates` | note:clinical |
| GET | `/note-templates/all` | org:manage |
| POST | `/note-templates` | org:manage |
| PUT | `/note-templates/{template_id}` | org:manage |

### Organisations, facilities, departments

| Method | Path | Permission |
|---|---|---|
| POST | `/organisations` | platform:organisations |
| GET | `/organisations` | platform:organisations |
| GET | `/organisations/current` | org:read |
| GET | `/facilities` | facility:read |
| POST | `/facilities` | facility:manage |
| GET | `/facilities/{facility_id}` | facility:read |
| PATCH | `/facilities/{facility_id}` | facility:manage |
| GET | `/departments` | department:read |
| POST | `/departments` | department:manage |

## Two-step sign-in (migration 0015)
Authenticator-app TOTP (RFC 6238: SHA-1, six digits, 30 seconds, one step either side allowed) with eight single-use recovery codes.
- `GET /auth/mfa` returns `{enabled, recovery_codes_remaining}`.
- `POST /auth/mfa/enroll` returns a new `secret` and an `otpauth_uri`. The secret is stored encrypted but does not count until confirmed. Calling it again before confirming replaces the secret.
- `POST /auth/mfa/confirm` `{code}` switches it on and returns the recovery codes once; only their hashes are kept.
- `POST /auth/mfa/disable` `{password, code}` needs the password and a current code or a recovery code.
- `POST /auth/login` for a user with it on answers 401 with error title `mfa_required` until `mfa_code` is supplied; a wrong code gives `invalid_mfa_code` and counts towards the account lockout. A code is accepted once (the newest accepted time step is stored, so a replay fails).
- `POST /users/{id}/mfa/reset` (`user:manage`) clears a colleague's second factor after a lost phone and lost recovery codes. It is audited as `MFA_RESET_BY_ADMIN`.

## Repeated requests

`POST /invoices/{id}/payments`, `/credit-notes` and `/refunds` accept an optional `Idempotency-Key` header of 8 to 100 characters. Send a new key for each intended action and the same key when retrying it. The first request with a key does the work; a repeat returns the invoice as it stands and records nothing. A request that is refused does not use up its key. Keys are scoped to the user, the invoice and the kind of action, and are deleted after two days.

A request refused because a monthly allowance is used up returns 409 with `"title": "usage_limit_reached"`.


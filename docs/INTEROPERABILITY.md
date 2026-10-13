# Interoperability (Phase 6)

## What is built
A **read-only FHIR R4 export** of the clinical record, as base resources. It is for the organisation's own
authorised users (permission `fhir:export`, held by doctors) and it **transmits nothing to anyone**.

| Endpoint | Returns |
|---|---|
| `GET /api/v1/fhir/metadata` | CapabilityStatement (draft; says no ABDM profile conformance is claimed) |
| `GET /api/v1/fhir/Patient/{id}` | Patient |
| `GET /api/v1/fhir/Encounter/{id}` | Encounter (the encounter's own doctor) |
| `GET /api/v1/fhir/Encounter/{id}/$export-document` | document Bundle: Composition first, then every resource it refers to (completed visits only, the encounter's own doctor) |

Errors on these routes are FHIR `OperationOutcome`s, not the problem+json used elsewhere. Every export writes an
audit row (no clinical content).

Resources produced: Patient, Practitioner, Organization (the facility), Encounter, Observation (vitals and lab
results), Condition, AllergyIntolerance, MedicationStatement, MedicationRequest, ServiceRequest, Composition.
Code: `app/modules/interop/` (`fhir.py` is pure mapping with no database access).

## Rules the export follows
- **Only settled data leaves.** Superseded versions and rejected facts are excluded. Draft prescriptions and draft
  orders are excluded. AI candidates and suggestions are never exported. Only SIGNED prescriptions and
  placed/resulted/cancelled orders appear.
- **Provenance and uncertainty travel with each fact** as `meta.tag`s (source, verification state), and as FHIR
  statuses: a SUSPECTED diagnosis is `unconfirmed`, a POSSIBLE allergy is `unconfirmed`, a provisional diagnosis is
  `provisional`. A receiver can tell patient-reported from clinician-confirmed.
- **Minimum necessary.** Patient carries name, gender, birth date (flagged when estimated), MRN, phone and language.
  The address and the (encrypted) ABHA number are not exported.
- **Codes only where the standard fixes them.** LOINC and UCUM for eight vital signs, as in the FHIR core
  vital-signs profile; FHIR/HL7 core code systems for statuses; everything else is free text. Glucose and pain
  score are uncoded on purpose. A diagnosis or medicine is coded only if a code and system were recorded with it
  (none are yet: no terminology service is connected).
- Narrative is XML-escaped.

## What is NOT built, and why
- **ABDM / NRCeS profile conformance.** The ABDM FHIR Implementation Guide (nrces.in) is the authority, but its
  pages could not be fetched from the build environment, so no profile constraint was read. From search
  snippets only: it is based on FHIR R4 (4.0.1), its clinical artefacts are Composition-based (for example
  PrescriptionRecord, DiagnosticReportRecord, DischargeSummaryRecord, WellnessRecord, OPConsultRecord), its
  DocumentBundle requires a Composition first, and several versions exist (5.0.0, 6.0.0, 6.5.0 and a 7.0.0
  preview were all seen). **Which version applies, and each profile's required elements, value sets and
  Composition.type codes, must be read from the IG before any `meta.profile` is asserted.** The Composition here
  uses LOINC 11488-4 "Consult note" as a stand-in type.
- **No ABDM integration at all.** ABHA creation/verification, the consent manager and consent artefacts, health
  information provider/user flows, facility and HPR registration, and the gateway. These need sandbox access,
  credentials, registration with ABDM, and the current official specifications. No endpoint, payload or flow has
  been written from memory. Sharing data outside the organisation additionally needs the patient's consent
  artefact; nothing here bypasses that.
- No FHIR write API, search, `$everything`, Provenance resources, Subscriptions, or SMART authorisation.
- No FHIR validator run. Output is checked structurally against the `fhir.resources` R4B models (FHIR 4.3.0, the
  nearest available to 4.0.1) in tests; that catches wrong types and unknown fields but **not** invalid code
  values or profile rules. The HL7 validator with the ABDM package should run in CI once the IG is available.
- Identifier systems use a placeholder namespace (`https://aarogyaos.example/fhir/...`). Replace with the
  organisation's registered systems.

## To go further (needs you)
1. Read the ABDM IG version your target requires and confirm the profiles to implement.
2. ABDM sandbox registration and credentials (client id/secret), and the current gateway/consent-manager docs.
3. A decision on how patients give and revoke consent for sharing (ties to the consent module's purposes).

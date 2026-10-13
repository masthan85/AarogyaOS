# Clinical AI Architecture

AI is advisory. Pipeline:

Transcript (final segments) → Clinical extraction → Patient context retrieval →
Terminology normalisation → Knowledge retrieval (approved sources only) →
LLM reasoning → **Deterministic safety checks** → Suggestion → Clinician review →
Decision → Action → Audit.

## Tasks (not one mega-prompt)
ClinicalExtractionTask, ConsultationSummaryTask, DifferentialSupportTask,
InvestigationSuggestionTask, MedicationSafetyTask, PatientSummaryTask,
TranslationTask. Each has a versioned prompt, a Pydantic output schema, schema
validation with reject-on-invalid (no free-text stored as fact), token/cost
metering and eval fixtures.

## Providers
`LLMProvider`, `EmbeddingProvider`, `TranslationProvider`, `TerminologyProvider`,
`ClinicalKnowledgeProvider`, `MedicationKnowledgeProvider` — all Protocols with
dev/fake adapters for tests. No business logic imports a vendor SDK.

## Clinical State
`PatientClinicalState` is a projection of facts, each carrying
`source ∈ {PATIENT_REPORTED, STAFF_ENTERED, DOCTOR_ENTERED, DEVICE_RECORDED,
LAB_RESULT, EXTERNAL_RECORD, AI_EXTRACTED}` and
`verification ∈ {UNVERIFIED, AI_GENERATED, REQUIRES_REVIEW, CLINICIAN_CONFIRMED,
CLINICIAN_EDITED, CLINICIAN_REJECTED}`, plus certainty (`CONFIRMED|POSSIBLE|NEGATED|
HISTORICAL`), evidence (transcript segment ids), and extraction version. Uncertain
patient statements ("might have had a penicillin allergy as a child") become
`POSSIBLE, REQUIRES_REVIEW`.

## Safety layer (no LLM dependence)
Allergy–drug cross-check (including unconfirmed/possible allergies → warn),
interaction and contraindication checks against a licensed medication knowledge
provider, dose-range checks, lab reference ranges, critical value flags. If the
knowledge provider is unavailable the UI says checks did not run; it never says "safe".

## Suggestions
Fields: category, title, explanation, supporting context refs, evidence/source,
uncertainty, created_at, model+prompt version, status
(PENDING/ACCEPTED/EDITED/REJECTED/DISMISSED), actor and timestamps per action.
Accepting a suggestion creates a *draft* object, never a signed order.

## RAG
Approved corpus only; metadata: source, publisher, document, version, publication
and effective dates, country, specialty. No open web search in production decision
support. Licensing of guideline content must be checked per source.

## Evaluation
Extraction: symptom/medication/allergy/negation/duration/severity/history accuracy,
hallucination and omission rates. Suggestions: unsafe-rate, unsupported-rate,
acceptance/edit/reject (never optimised alone). Eval suites run in CI against
fixtures with fake providers; live-model evals run on demand.

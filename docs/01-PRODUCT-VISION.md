# Product vision

This document records what AarogyaOS is meant to be, who it is for and what it deliberately refuses to do. It is written from the repository: the original architecture baseline (`03-SYSTEM-ARCHITECTURE.md`, section 1 and the non-negotiables below), the hazard log in `CLINICAL_SAFETY.md` and the code as it stands. Where the repository does not say something, for example pricing or target market size, this document says so rather than guessing.

## The idea

AarogyaOS is an operating layer for the care journey of a patient in an Indian clinic or hospital: from arriving at the front desk, through triage and the doctor's consultation, to tests, prescription, billing and follow-up. The part that makes it different from a conventional record system is that the consultation itself can be the source of the record. With the patient's consent, a doctor can record the conversation. The system transcribes it in the languages Indian clinics actually hear, including conversations that switch between languages mid-sentence, and proposes structured entries (symptoms, history, medicines, allergies, plan) for the doctor to accept, edit or reject. Nothing proposed by software becomes part of the patient's record until a clinician has decided.

The working name for the idea in the code is the "clinical interaction session": a recording that always has an identified patient, an encounter, a declared purpose, consent for that purpose and an explicit start and stop. Everything else in the product is built around making that session safe, auditable and optional.

## Who it is for

The primary users are staff in small and mid-sized clinics and hospitals in India:

- Doctors, who want less typing during a consultation without giving up control of the record.
- Nurses, who record triage and vitals and, with a doctor's confirmation, vaccines and similar facts.
- Receptionists and billing staff, who register patients, manage the queue and issue invoices, and who should never see clinical content.
- Pharmacists and laboratory or radiology technicians, who each need a narrow, role-specific view.
- Administrators, who configure the organisation, staff, consent wording, note layouts and reference material, and who can read the audit log but not patient records.

Patients are indirect users today. They give or withdraw consent, receive printed or shared documents (prescriptions, visit summaries, referral letters, invoices) and can have a summary translated into their language, but there is no patient-facing app or portal.

## Problems it addresses

Documentation burden is the headline problem. A doctor in a busy outpatient clinic often types or dictates notes while the patient waits, or writes them later from memory. Free-text systems also lose information about where a statement came from: did the patient say it, a nurse measure it, or a doctor conclude it?

The second problem is language. Many consultations mix a regional language with English medical terms, and general-purpose transcription handles that poorly. The product treats language as data (each segment carries its detected language, any secondary language and code-mixing information) and keeps the original transcript untouched while allowing human corrections as a separate layer.

The third is trust. Clinical staff are right to distrust a system that writes into the record on its own. The design therefore keeps every AI output in a review queue outside the record, requires exact quotes from the conversation as evidence for each proposed entry, preserves negations and uncertainty ("denies chest pain", "maybe a fever") instead of flattening them, and records on every fact where it came from and whether a clinician verified it.

The fourth is that small clinics rarely have one system for the whole journey. The product therefore also covers registration, scheduling, queue, orders and results, prescriptions, pharmacy dispensing records and billing, so that the same patient identity and permissions apply throughout.

## Principles that shape every decision

These are the non-negotiables from the architecture baseline. They are enforced in code and tested, not just stated.

1. AI is decision support. It never diagnoses, prescribes, orders, refers or discharges. Where a model suggests an investigation, accepting the suggestion creates a draft order that a doctor must still place.
2. Every workflow works with AI, speech and the network features switched off. A clinic can run the product on paper-equivalent data entry alone.
3. Recording happens only inside a consented, identified, purposeful session with an explicit start and stop, and the indicator reflects the real microphone and connection state.
4. The raw transcript is never discarded or rewritten. Normalised or corrected text is a derived layer.
5. Provenance and verification state exist on every clinically material fact. Corrections add a new version; history is append-only and enforced by the database.
6. Authorisation and tenant isolation are enforced on the backend, with PostgreSQL row-level security as a second line of defence.
7. Minimum necessary data, and the simplest architecture that meets the requirement: a modular monolith, not microservices.
8. Never invent medical codes, provider capabilities, drug data or tax rules. Where a licensed source is missing, the feature is absent or says what it cannot check.

## Intended benefits

For doctors, the benefit is a draft note assembled from the conversation, laid out like a clinic note, with each line traceable to the words it came from. For clinics, it is one consistent patient identity and permission model across the front desk, clinical work, pharmacy and billing. For patients, it is consent that is specific (eight separate purposes, none implying another), withdrawable and effective immediately, and documents they can understand in their own language. For the organisation, it is an audit trail that records who did what without storing clinical content in logs.

The repository does not contain commercial objectives such as target customers, pricing or revenue goals. The only commercial constraint it records is cost awareness: speech and model usage is metered per organisation from the start, because per-minute speech cost has to fit Indian clinic price points (`03-SYSTEM-ARCHITECTURE.md`, risk table).

## What exists today against the vision

The full workflow is built and tested end to end against synthetic data, including the consultation flow with a development speech provider and a development language model. The Sarvam speech-to-text adapter has run once against the live service with a short English clip; translation, read-aloud and the Sarvam chat model have run live once each. The Anthropic adapter has never been run against the real API. The microphone streaming module has never run on a physical device. Nothing has been deployed, and no clinical, legal or security review has taken place. `12-FEATURE-STATUS.md` has the evidence for each claim and `README.md` summarises the same position.

## Scope boundaries

Out of scope by design, in line with the original baseline: autonomous AI actions of any kind, training models on customer data, hospital inpatient management (beds, ICU, theatre), laboratory and radiology information systems and image archives, pharmacy stock management, a full patient app, population analytics and research use, and microservices or message brokers.

Out of scope until outside input exists: ABDM integration (needs the official implementation guide version and sandbox credentials; the owner has paused this), coded diagnoses and medicines (needs a licensed terminology service), drug interaction and dose checking (needs a licensed drug knowledge source), sending claims to insurers, online payment collection, and any legally recognised digital signature.

## Roadmap in one paragraph

The next work is validation rather than features: run the microphone and speech stack on real devices and real Indian-language audio, run the language-model adapter against the live API under a signed data agreement, have a clinician and a legal adviser review the consent wording and clinical safety log, and deploy to a staging environment with TLS, a proper object store for audio and a shared rate limiter. After that, the roadmap in `14-ROADMAP.md` covers interoperability with ABDM, terminology and drug knowledge integration, and the patient-facing surface. The itemised, prioritised list is in `13-PRODUCT-BACKLOG.md`.

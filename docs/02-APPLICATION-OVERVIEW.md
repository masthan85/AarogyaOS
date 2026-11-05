# Application overview

This is the tour of what the product does, who does it and where it lives in the codebase. For the reasoning behind it see `01-PRODUCT-VISION.md`; for how it is built see `03-SYSTEM-ARCHITECTURE.md`; for what is finished and what is not see `12-FEATURE-STATUS.md`.

## The two deliverables

AarogyaOS ships as two programs in one repository. `services/api` is a FastAPI service backed by PostgreSQL that holds all data and enforces every rule. `apps/mobile` is an Expo and React Native app (Android first, iOS compatible, tablet aware) that talks only to that API. There is no other client and no other path to the data. The app also builds for the web through React Native Web, which the redesign work used for screenshots, but the web build is not a supported product target.

## Roles

Roles are stored in the database and seeded from `services/api/app/modules/identity/permissions.py`. Every endpoint declares the permission it needs and the server checks it. The mobile app hides screens a role cannot use, but that is a convenience only.

| Role | What they can do | Deliberately cannot do |
|---|---|---|
| Doctor | Run consultations on their own encounters, write notes, diagnoses, procedures, referrals, orders and prescriptions, sign, review results, record and review AI-assisted sessions, approve summaries and letters, export FHIR | Write into another doctor's consultation, sign for someone else |
| Nurse | Triage, vitals, triage notes, allergies and medicine history, vaccines (a doctor confirms them), correct transcript wording | Diagnose, prescribe, confirm procedures or referrals |
| Receptionist | Register and search patients, appointments, walk-ins, check-in, queue, capture consent, start non-clinical sessions, read and write billing | Open the clinical timeline or any clinical record |
| Billing staff | Invoices, payments, credit notes, refunds, price list, GSTIN, claim tracking, end-of-day cash count | Any clinical content |
| Pharmacist | Look up signed prescriptions and record dispensed, partly dispensed or not dispensed | Stock, brands, batches, interaction checks (none exist) |
| Lab and radiology technician | See their own department's placed orders and enter structured results | See other departments' orders or drafts |
| Clinic or hospital administrator | Organisation settings and policy, facilities, departments, staff, roles, doctor profiles and hours, note layouts, consent wording, reference library, usage, audit log, legal holds, price list | Any patient record |
| Platform administrator | Create organisations | Anything inside an organisation |

Doctor cover is a narrow exception to ownership: a doctor can ask a colleague to review their results for up to 31 days, and a doctor can hand an open consultation to another doctor at the same facility.

## A day in the clinic

A patient arrives and reception searches by phone number, MRN or name. The search returns minimal fields only (masked mobile, age, sex). A new patient is registered with duplicate detection; the ABHA number, if given, is stored encrypted. Reception books an appointment or creates a walk-in, checks the patient in, and the patient joins a per-facility, per-doctor queue with a daily token number.

Before any recording, reception or a nurse captures consent. Consent is per purpose (medical care, audio recording, speech transcription, AI processing, audio retention, research, analytics, model improvement), carries the wording version shown and the language used, and can be captured by a guardian for a minor. Withdrawal takes effect immediately and ends any live stream.

The nurse opens the encounter for triage, records vitals (with Celsius and Fahrenheit conversion, plausibility limits and flags for abnormal or critical values), a chief complaint and allergies. The doctor takes the same encounter over for the consultation.

During the consultation the doctor may start a recording. Audio streams to the API over a WebSocket, through a provider-independent speech layer, and transcript lines appear on the Conversation tab. When recording ends, the assistant analyses the transcript and opens the Draft EMR tab: the visit laid out as a clinic note, each line showing the words it came from. The doctor accepts, edits or rejects each one. The same screens work by hand if recording or AI is off.

The doctor adds diagnoses with a stated certainty, procedures, vaccines and referrals if relevant, orders investigations and drafts a prescription. A safety check compares the prescription with the recorded allergies (by name; the check states what it cannot do) and the doctor acknowledges any warnings before signing. A signed prescription is frozen and sealed with a keyed hash so later tampering can be detected. The doctor finishes the visit after the app lists anything the assistant found that nobody has decided on.

Technicians enter results; the ordering doctor, or a covering colleague, reviews them with critical values first. Follow-ups appear on a worklist. The pharmacist records dispensing. After the visit, billing staff see the finished visit in a "to bill" list, issue a numbered invoice, record payments and, if needed, credit notes and refunds. The doctor can approve a patient-friendly visit summary or a referral letter, optionally translated and read aloud, and share or print it as a PDF.

## Capability map

| Area | What it covers | Backend module | Main mobile screens |
|---|---|---|---|
| Identity and tenancy | Organisations, facilities, departments, users, roles, login, refresh, audit | `identity`, `tenancy`, `audit` | Login, Settings, Admin |
| Patients | Registration, duplicate detection, search, identifiers, languages, timeline | `patients` | Patients, patient profile |
| Scheduling | Practitioners, working hours, slots, appointments, walk-ins, check-in, queue | `scheduling` | Appointments, Queue |
| Clinical record | Encounters, vitals, notes, diagnoses, allergies, medicines, prescriptions, orders, results, follow-ups, procedures, vaccines, referrals | `clinical` | Triage, Consultation tabs |
| Consent | Policy wording, consents, guardians, withdrawal | `consent` | Consent screen |
| Speech | Sessions, audio gateway, transcripts, speakers, corrections, retention | `interactions`, `app/speech` | Conversation tab, recording bar |
| Clinical AI | Extraction, guardrails, review queue, suggestions, reference knowledge, chart questions | `ai`, `app/ai` | Draft EMR, Assist |
| Documents | Visit summaries, referral letters, translation, read-aloud | `summaries` | Documents tab |
| Templates | Note layouts | `templates` | Notes tab, Admin |
| Pharmacy | Dispensing records | `pharmacy` | Pharmacy |
| Billing | Invoices, payments, tax lines, credit notes, refunds, price list, claims, day close | `billing` | Billing, Invoice, Price list, End of day |
| Interoperability | Read-only FHIR R4 export of a completed visit | `interop` | Copy visit as text (FHIR is API only) |
| Retention | Legal holds | `retention` | Patient profile |
| Cover and handover | Doctor cover, consultation handover | `cover`, `clinical` | Cover, Consultation |
| Operations | Health, readiness, metrics, scheduled jobs, backups | `core`, `ops`, `jobs.py` | none |

## Where things live

```
AarogyaOS/
  apps/mobile/            Expo Router app, TypeScript strict
    src/app/              routes (login, home, patients, queue, consultation, billing, admin ...)
    src/features/         screens and feature components, one folder per area
    src/domain/           pure logic with unit tests (billing, dosing, EMR draft, print ...)
    src/api/              typed client, zod schemas and endpoint functions
    src/design-system/    tokens and components
    src/services/         device services: secure token store, biometrics, print, audio capture
  services/api/           FastAPI modular monolith
    app/core/             config, database and tenancy context, crypto, security, errors, rate limits
    app/modules/          one folder per business area (models, schemas, service, router)
    app/speech/           speech provider interface, Sarvam and development providers, live hub
    app/ai/               language model providers, prompts, guardrails, extraction
    alembic/versions/     14 migrations (0001 to 0014)
    tests/                38 test modules, 504 tests
    scripts/              live checks, smoke test and load test
  infrastructure/         Docker Compose, Postgres role init, backup and restore-drill scripts
  docs/                   this documentation, decision records and design screenshots
```

## Languages and providers

Supported languages are rows in a `languages` table, not code. Speech-to-text runs through a `SpeechProvider` interface with Sarvam (live adapter) and a synthetic development provider. Language models run through an `LLMProvider` interface with Sarvam, Anthropic, a self-hosted OpenAI-compatible server, and a development stand-in. Translation and text-to-speech use Sarvam and are off until chosen. Every provider is off or synthetic unless configured, and production refuses to start with a development provider selected. `06-CONFIGURATION.md` lists the switches and `SARVAM.md` explains what is and is not sent to Sarvam.

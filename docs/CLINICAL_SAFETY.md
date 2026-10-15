# Clinical Safety

Principles: clinician control over automation; uncertainty visible; AI output never
becomes a confirmed fact without clinician action; deterministic checks for
high-risk logic; manual workflow always available.

Hazard log (initial)
| ID | Hazard | Control |
|---|---|---|
| H1 | AI-extracted allergy/medication wrong | Candidate state, mandatory review, source+evidence link |
| H2 | Mis-transcribed negation or dose | Confidence flags, raw text one tap away, review gate |
| H3 | Missed interaction because AI/knowledge service down | UI states checks not run; no "safe" claim |
| H4 | Automation bias | Suggestions framed "for consideration", rank limits, reject tracking |
| H5 | Wrong patient recorded | Patient header always visible; session bound to patient+encounter |
| H6 | Recording without consent | Server-side consent gate, visible indicator |
| H7 | Translation changes meaning | Preserve clinician-approved source text, flag uncertainty |
| H8 | Cross-tenant disclosure | Tenant scoping, RLS, tests |

## Phase 3 hazards (clinical record)
| ID | Hazard | Control | Residual risk / open item |
|---|---|---|---|
| H9 | Wrong value from unit confusion (°F entered as °C) | Fahrenheit accepted and converted; original value kept; hard plausibility limits reject impossible numbers | Plausible-but-wrong values still pass; clinician judgement |
| H10 | Abnormal vital missed | Deterministic flags from a versioned reference table; critical/abnormal values raise ranked alerts in the clinical state | **Reference ranges are provisional defaults, not clinically signed off.** Children get no interpretation (UNKNOWN) by design |
| H11 | Prescribing against a known/possible allergy | Allergy name match against confirmed, possible, historical and *unverified* allergies; unrecorded allergy status is itself a blocking warning; each warning must be acknowledged by code before signing | Name matching only. Drug-class cross-sensitivity (e.g. amoxicillin vs penicillin) is **not** detected until a medication knowledge provider is connected |
| H12 | "No warnings" read as "safe" | Every safety result carries a CHECKS_LIMITED notice listing what was not checked (interactions, contraindications, dose range, cross-sensitivity); stored in the signed snapshot | Depends on clinician reading the notice |
| H13 | Unsigned/half-made decisions leaking into care | Drafts (prescriptions, orders) are invisible to pharmacy, lab and nurses; a visit cannot be completed with drafts outstanding | — |
| H14 | Silent alteration of the record | Facts append-only (database triggers); corrections supersede; signed prescriptions and reported results frozen; audit log append-only | A database superuser could still bypass triggers; restrict and monitor superuser access |
| H15 | Unverified information treated as confirmed | Every fact carries source + verification state; a patient's uncertain statement is stored as POSSIBLE; only a doctor confirms diagnoses | AI-generated facts (Phase 5) must enter as AI_GENERATED / REQUIRES_REVIEW |
| H16 | Doctor edits another doctor's consultation | Clinical writes restricted to the encounter's own practitioner | Cover/handover workflow not built |
| H17 | Offline duplicate or lost clinical writes | Clinical writes are never queued offline; the app says plainly when nothing was saved | Idempotency keys planned |

## Phase 4 hazards (speech)
| ID | Hazard | Control | Residual risk / open item |
|---|---|---|---|
| H18 | Recording without valid consent | Server-side gate at create, start, resume, connect and on a timer; per-purpose consent; guardian required for minors | Consent *wording* is a template pending legal review; guardian rules need counsel |
| H19 | Screen says "recording" when it is not (dropped link, crash) | Indicator derived from live+mic+socket; server pauses on drop; shielded cleanup; stale sessions auto-paused | Needs device testing on poor networks |
| H20 | Wrong speaker attribution (e.g. family member answers) | Roles start UNKNOWN, set by a person, audited; never inferred from order | Humans may mislabel; diarisation quality unmeasured |
| H21 | Mis-heard negation, dose, drug or allergy in a regional language / code-switched speech | Raw text kept; low-confidence lines flagged; transcript is NOT a clinical fact; extraction (Phase 5) must be reviewed | **No real ASR accuracy data exists yet.** Do not pilot clinically before measuring on reviewed recordings |
| H22 | Synthetic transcript reaching a real record | Development provider refused in production; UI badge; DEVELOPMENT chip on every bar | Config discipline |
| H23 | Audio kept longer than the patient agreed | Default discard; retention needs policy AND consent; encrypted; scheduled purge; withdrawal queues deletion | Purge job must actually be scheduled (Phase 7) |
| H24 | Over-reliance on AI summaries | AI processing is a separate, optional consent and org switch; partials never stored | Phase 5 controls |
| H25 | A reception conversation leaking clinical content into the record | Reception transcripts visible only to whoever recorded them; Phase 5 extraction must be purpose-limited | Not yet enforced in extraction (none exists) |

## Phase 5 hazards (clinical AI)
| ID | Hazard | Control | Residual risk / open item |
|---|---|---|---|
| H26 | Model invents a finding | Every candidate must quote the transcript exactly; ungrounded items are dropped; nothing enters the record unreviewed | A real quote can still be misunderstood; the clinician must read the quote shown |
| H27 | Negation lost ("no chest pain" becomes "chest pain") | Assertion is explicit (PRESENT / ABSENT / POSSIBLE / HISTORICAL); negation-cue flag; UI shows "Patient denies"; absent allergy or medicine becomes a note, never an allergy or medicine fact | Negation in Indian languages is only covered by a small cue list. Measure on real transcripts |
| H28 | Patient's uncertain statement recorded as fact | Hedged wording is downgraded to POSSIBLE; accepted facts carry source AI_EXTRACTED | Hedge cues are lexical |
| H29 | Clinician's question or a relative's remark attributed to the patient | Clinician speech is not extracted as patient statements; unassigned speaker is flagged | Depends on speaker labels set by a person |
| H30 | AI suggestion mistaken for an instruction or a diagnosis | Wording rules reject "prescribed/ordered/diagnosed"; diagnoses can only be SUSPECTED; investigations and prescription items only DRAFT; UI states what accepting does | Alert fatigue and automation bias remain; track acceptance by category |
| H31 | Unsafe suggestion from the model (interaction, contraindication, allergy) | Model may not emit safety categories; those come only from deterministic rules; a model medicine matching an allergy becomes a warning | **No drug knowledge base is connected, so interactions and contraindications are not checked at all.** The UI must not imply they were |
| H32 | Suggestion rests on stale, wrong or unlicensed guidance | Approved documents only, two-person approval, versions and dates shown with each citation, retirement | Content correctness is the approvers' responsibility; no clinical content is shipped |
| H33 | Allergy cross-sensitivity missed | Name match only, and the warning says so | Drug-class checks need a medication knowledge provider |
| H34 | Wrong or fabricated translation reaches a patient | No translation provider is connected; summaries are not translated and say so; a doctor approves final wording | When one is connected, translated medication instructions need a human check |
| H35 | AI outage during care | Everything is optional; failures return a calm message; no clinical write depends on AI | — |
| H36 | Cost or quota runaway | Per-session rate limit, hard timeout, per-call usage rows | Costs are NULL until a real price is configured |
| H37 | Development extractor mistaken for a real model | Refused in production; `is_development` on every run; badge in the UI | Config discipline |

## Templates, letters and chart questions
| ID | Hazard | Control | Residual risk / open item |
|---|---|---|---|
| H38 | A template puts words in a record the doctor did not write | Templates hold headings and hints only; nothing is pre-filled; each saved section is an ordinary doctor-entered note | A doctor can still type carelessly into a familiar layout |
| H39 | A referral letter states a suspicion as a diagnosis, or hides uncertainty | Built by code from recorded data: certainty is printed with each diagnosis and allergy; unverified or patient-reported items are labelled; allergy status is always stated (none / unknown); doctor edits and approves; no model writes it | The letter reflects the record: wrong data in gives wrong letter out. Sending is not built, so a printed or copied letter has no further controls |
| H40 | The chart answer invents or misattributes a fact | Answer comes only from listed chart entries; every statement must cite entries that exist, else it is dropped; "not found" instead of a guess; the matching entries are shown beside it; the model cannot claim actions | A cited entry can still be misread by the model; the clinician sees the cited source text and should check it |
| H41 | Unreviewed AI output treated as chart fact | Candidates and suggestions are excluded from the searchable chart (tested) | — |
| H42 | Stale or superseded entries answer a question | Only current, non-rejected versions are searched, each with its date | Very old entries are still returned if they match |

## Translation and read-aloud (Sarvam)
| ID | Hazard | Control | Residual risk / open item |
|---|---|---|---|
| H43 | A machine translation changes a dose, drug or instruction and the patient follows it | Always a draft until a doctor approves; digits requested in 0-9 and compared with the English (mismatch flagged `NUMBERS_MISMATCH`); the English source is kept; editing marks it clinician-edited | **Not clinically evaluated.** Numbers are checked, words are not. A doctor who cannot read the language cannot check it: use a reader for each language you offer |
| H44 | Audio of text nobody approved, or in the wrong language, is played to a patient | Only APPROVED text is spoken; the document's own language is used; unsupported languages are refused; audio is not stored | Pronunciation of drug names and numbers is unverified; the voice is synthetic and says nothing about who approved it |
| H45 | Patient text sent to a vendor without permission | Needs the organisation's AI switch, the patient's AI-processing consent and the provider switch; checked per call; nothing sent when any is missing (tested) | Vendor retention and residency terms are not yet agreed |

A clinical safety officer (e.g. under DCB0129/0160-style practice, adapted to India)
and a regulatory review (CDSCO SaMD status) are required before any clinical pilot.

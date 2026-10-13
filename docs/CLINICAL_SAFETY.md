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

A clinical safety officer (e.g. under DCB0129/0160-style practice, adapted to India)
and a regulatory review (CDSCO SaMD status) are required before any clinical pilot.

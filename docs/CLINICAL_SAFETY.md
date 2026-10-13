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

A clinical safety officer (e.g. under DCB0129/0160-style practice, adapted to India)
and a regulatory review (CDSCO SaMD status) are required before any clinical pilot.

# Clinical AI Architecture (Phase 5)

AI here is **decision support and drafting help only**. It never diagnoses, prescribes, orders, refers or
discharges. The whole consultation works with AI switched off, unavailable or failing.

## What exists

```
transcript (immutable final segments)
   -> ClinicalExtractionTask (LLMProvider)          app/modules/ai/extraction.py
   -> deterministic guardrails                       app/ai/guardrails.py
   -> CANDIDATES (a review queue, outside the record)
   -> clinician accepts / edits / rejects            app/modules/ai/review.py
   -> ordinary clinical fact: source AI_EXTRACTED, evidence_segment_ids, verification
      CLINICIAN_CONFIRMED or CLINICIAN_EDITED

patient record (+ pending candidates) + approved reference passages
   -> deterministic rules (always)                   app/modules/ai/suggestions.py
   -> SuggestionTask (LLMProvider, optional)
   -> vetting -> SUGGESTIONS -> clinician acts       (accept / edit / reject / dismiss)
```

Candidates and suggestions are **not** part of the Patient Clinical State. Nothing the model produced is
read by safety checks, summaries or the record until a clinician has acted on it (ADR-0008).

## The model is untrusted
Output is parsed strictly (one JSON object, optional code fence, never "repaired"). If the envelope is
invalid the run is recorded as failed and nothing is kept. Candidates are then vetted one at a time:

| Rule | Effect |
|---|---|
| must match the schema (`extra=forbid`) | drop `invalid_schema` |
| kind must be allowed for the session purpose (reception sessions cannot yield clinical facts) | drop |
| every evidence quote must appear verbatim in the cited segment | drop `unsupported_evidence` |
| a question is not a statement of fact | drop `from_question` |
| hedged wording ("maybe", "I think", "shayad") | assertion downgraded to POSSIBLE |
| negation cue near the term but assertion PRESENT | flagged `negation_cue_check` |
| unassigned speaker | flagged `speaker_unassigned` |
| attributes outside a per-kind whitelist | removed, flagged |
| duplicates (within the run and against earlier runs) | dropped |

Suggestions are vetted the same way: unknown supporting references, unknown source ids, text claiming an
action ("I have prescribed..."), and **any safety category from the model** (allergy, interaction,
contraindication) are dropped. Clinical advice categories need an approved source when the organisation
policy `ai_suggestions_require_source` is on (the default). A model suggestion that names a medicine
matching a recorded allergy is converted into an allergy warning; one matching a current medicine gets a
duplicate-therapy note.

## What accepting does
| Candidate / suggestion | Result |
|---|---|
| symptom, history, examination, vital mentioned, follow-up | clinical note of the right type |
| allergy / medicine (PRESENT) | allergy / patient-medication fact; ABSENT becomes a note ("denies...") |
| diagnosis discussed | condition with certainty **SUSPECTED** only; doctor only |
| investigation discussed or suggested | **DRAFT** service request; never placed |
| treatment discussed | plan note, or a **DRAFT** prescription item (then the normal safety check and signing apply) |
| other suggestion categories | acknowledgement only; no record is created |

Nurses may review only triage-level kinds; everything else needs the encounter's own doctor. Review
decisions are final and enforced by database triggers; the candidate text and evidence cannot change.

## Deterministic suggestions (no model)
Allergy status not recorded; current medicines not recorded; no chief complaint; abnormal vitals;
abnormal results; discussed treatment or medicine whose name matches a recorded allergy (name match only,
and the warning says so).

## Reference knowledge (RAG)
Organisation-supplied documents with publisher, version, dates, country, specialty and licence
(`ORG_LICENSED | PUBLIC_DOMAIN | SYNTHETIC_TEST`). Nothing is fetched from the web. A document is used
only after **a different person with `knowledge:manage` approves it**, and stops being used when retired
or before its effective date. Retrieval embeds the query and ranks chunks by cosine similarity **in Python**
(pgvector is not installed in the development database); it sits behind `EmbeddingProvider` so pgvector can
replace it in Phase 7 (ADR-0009). Minimum similarity applies, so irrelevant material is not injected.

## Providers
`LLMProvider`, `EmbeddingProvider`, `TranslationProvider`, `TerminologyProvider`,
`MedicationKnowledgeProvider` are Protocols (`app/ai/`). Registered implementations:

| Provider | Status |
|---|---|
| `development` LLM (lexicon extractor, deliberately naive) | built; refused in production; exists to exercise the guardrails |
| `development` embeddings (feature hashing; lexical, not semantic) | built; refused in production |
| `anthropic` LLM (Claude, official SDK, `app/ai/anthropic_llm.py`) | **built, not run against the real API.** Enabled by `AAROGYA_LLM_PROVIDER=anthropic` + `AAROGYA_ANTHROPIC_API_KEY`; default model `claude-opus-5-5` (`AAROGYA_ANTHROPIC_MODEL`). Refusals and truncated answers are errors; no sampling parameters are sent (the current models reject them). Needs, before patient data: a signed data-processing agreement, a residency decision and an eval run |
| OpenAI, Azure OpenAI, Google, self-hosted LLM | **not built** |
| Real embeddings, translation, terminology (SNOMED/ICD/LOINC), medication knowledge | **not built**; the Null providers raise `NotAvailable` and the UI says so |

An unconfigured or failing provider yields "AI assistance is unavailable, carry on documenting manually".
Failures never raise into the consultation.

## Patient summary
Built **without a model**: signed prescription items, ordered tests, pending follow-ups, settled
diagnoses (confirmed or provisional, doctor-entered or clinician-confirmed) and the doctor's own
instructions. Unreviewed AI output is never included. Translation goes through `TranslationProvider`; with
none connected the summary stays in the clinician's language and is marked `NOT_AVAILABLE`. A doctor edits
and approves; an approved summary is frozen by a trigger and superseded by newer approvals.

## Chart question and answer
`POST /patients/{id}/ai/ask` (`app/modules/ai/chartqa.py`). The chart is flattened into citable entries (current, non-rejected
diagnoses, allergies, medicines, vitals, notes, results, signed prescriptions, pending follow-ups; never AI candidates or
suggestions). The model sees the question and those entries without the patient's name. Its JSON answer is vetted: each
statement needs citations that exist, anything claiming an action is dropped, and if nothing survives the reply is "could not
be answered from the recorded chart". A keyword search over the same entries is always returned, so the feature works with AI
off, unconsented or failing. Rate-limited per user; audited (no question text) and metered like other AI calls.

## Control of automation
Per organisation: `ai_processing_enabled`, `ai_suggestions_enabled`, `ai_suggestions_require_source`.
Per session: `ai_processing` (needs the separate AI_PROCESSING consent, re-checked on every run). Per run:
rate limit (`AAROGYA_AI_ANALYSES_PER_MINUTE`) and a hard timeout (`AAROGYA_LLM_TIMEOUT_SECONDS`).

## Audit, events and metering
Every candidate/suggestion decision writes an audit row with `ai_involved` and an outbox event
(`AI_CANDIDATE_*`, `AI_SUGGESTION_*`, `PATIENT_SUMMARY_*`, `KNOWLEDGE_DOCUMENT_*`). Payloads carry kinds and
ids, never clinical text. `ai_usage` records provider, model, token counts (flagged when estimated), latency
and status per call, with no content; cost stays NULL until a real price is configured.

## Evaluation
`python -m app.ai.eval [file]` scores extraction against hand-labelled transcripts (`services/api/evals/`):
precision and recall per kind, negation accuracy, unsupported-extra rate, omission rate. **The bundled
fixtures are three small synthetic cases and the development extractor was written to pass them, so the
perfect score only shows the harness works.** Real evaluation needs clinician-labelled transcripts in the
languages served. Suggestion quality (unsafe / unsupported rate) has no gold set yet; at runtime every
dropped suggestion is counted. Acceptance rate is recorded but must never be optimised on its own.

## Self-hosted model (optional)

`AAROGYA_LLM_PROVIDER=self_hosted` with `AAROGYA_SELF_HOSTED_LLM_URL` and `AAROGYA_SELF_HOSTED_LLM_MODEL` sends the assistant's prompts to a model you run (vLLM, Ollama, llama.cpp server or anything speaking the chat-completions interface) instead of a vendor. Only that address is contacted: `https`, or plain `http` for localhost or a private-network address (a public address over `http` is refused at start-up). The same organisation switch and patient AI-processing consent apply, and every guardrail still runs on the output: strict JSON, schema checks, exact-quote grounding, hedging and negation rules, and clinician review.

Built against a fake server only. Which model to use is open: judge any candidate on clinician-labelled Telugu, Hindi, Urdu and English transcripts (`app/ai/eval.py`) before using it with patients. `AAROGYA_SELF_HOSTED_LLM_JSON_MODE=true` asks the server for JSON-only output; turn it on only if your server supports it. It lowers malformed replies but does not make a reply correct.

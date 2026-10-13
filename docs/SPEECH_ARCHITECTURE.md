# Speech Architecture

## Pipeline
Mobile audio (16 kHz mono PCM, 100–250 ms frames) → WebSocket audio gateway (auth,
consent re-check, session binding) → `SpeechProvider.stream_transcribe()` →
partial/final segments → persisted `TranscriptSegment` → SSE to doctor screen →
(finals only) extraction queue. Partials are display-only and never feed clinical state.

## Provider abstraction
```python
class SpeechProvider(Protocol):
    name: str
    capabilities: SpeechCapabilities          # declared, not assumed
    async def transcribe(audio, opts) -> TranscriptResult
    def stream_transcribe(opts) -> AsyncStream[SegmentEvent]
    async def detect_language(audio) -> LanguageGuess
    async def identify_speakers(audio, opts) -> list[SpeakerTurn]   # may be unsupported
    async def translate(text, source, target) -> Translation
```
`SpeechCapabilities` records: streaming, diarisation (batch/stream), word timestamps,
code-mixed output, language list, max duration, input formats. Callers check
capabilities and degrade (e.g. run batch diarisation after the session ends).
Unsupported calls raise `CapabilityNotSupported`; nothing is faked.
Selected with `SPEECH_PROVIDER=<name>`; optional `SPEECH_FALLBACK_PROVIDER`.
A `DevelopmentSpeechProvider` replays scripted synthetic transcripts and is
labelled as such in every response and UI badge.

## Stored per segment
speaker_id, speaker_role (DOCTOR/PATIENT/OTHER_STAFF/FAMILY_MEMBER/UNKNOWN; manually
correctable, with corrections audited), start_ms, end_ms, language, secondary_language,
language_confidence, code_switch spans, confidence (nullable), `raw_text`
(immutable), `normalised_text` (derived, versioned), provider, provider_model.

## Hard problems and approach
Code-switching, dialects, noise, overlap, family answering for patient: handled by
(1) provider choice per measured WER on our own synthetic+governed test sets,
(2) storing uncertainty, (3) low-confidence spans flagged for review, (4) speaker
role never inferred from order, (5) clinician verification of every extracted fact.

## Sarvam AI (evaluation, as of 2026-10; from official docs via search)
Confirmed in docs: Saaras v3 recommended (Saarika v2.5 legacy); 22 Indian languages
with automatic language detection; output modes include transcribe/translate/verbatim/
transliterate/codemix; batch API with diarisation; WebSocket streaming accepting WAV/PCM
at 16 kHz; Python and Node SDKs.
**Not yet confirmed (blockers for adapter):** streaming diarisation, per-language
quality, pricing, latency in our region, data-retention/training terms, DPA, healthcare
suitability, India data residency. docs.sarvam.ai was unreachable from the build
sandbox, so exact request/response schemas have NOT been read. The adapter is
therefore scheduled for Phase 4 after reading the live API reference; no
fabricated client exists in the repo.

## Evaluation
Separate from clinical AI: WER, medical-term error rate, language-ID accuracy, speaker
attribution, code-switch accuracy, per-dialect cohort results. Synthetic scripted
conversations across the 10 target languages; no real recordings without governance.

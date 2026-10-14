# Speech Architecture

Status: Phase 4 implemented around the provider boundary. **No real speech vendor is integrated yet.**
Everything below that says "development" is synthetic and exists to exercise the pipeline.

## Flow

```
Phone microphone (16 kHz mono PCM16)
  -> WebSocket /api/v1/interactions/{id}/audio     (auth = first message, consent re-checked on a timer)
  -> SpeechProvider.stream_transcribe()             (primary, optional fallback)
  -> partial segments: shown live, never stored     final segments: stored immutably
  -> GET /interactions/{id}/transcript (poll) | /events (SSE)
  -> Phase 5: extraction reads FINAL segments only
```

## Clinical Interaction Sessions

A recording is a bounded session (`clinical_interactions`): `CREATED -> ACTIVE <-> PAUSED -> ENDED`.
Creating one requires: an identified patient; a known visit (an encounter for triage/consultation, an
open appointment for reception); the right staff member for the purpose (`interaction:consultation`,
`:triage`, `:reception`) who, for consultations, is the encounter's own doctor; the organisation to have
recording enabled; **active consent for AUDIO_RECORDING and SPEECH_TRANSCRIPTION** (plus AI_PROCESSING if AI
assistance is requested, which the organisation must also have enabled); an available provider.
Recording begins only on an explicit **Start**, and stops on **Stop**/**Pause**. The consent rows relied on
are frozen into the session (`consent_ids`).

Deliberate deviation from the brief: "encounter is known" is satisfied at reception by the open *appointment*,
because no encounter exists until triage.

## Keeping the recording state honest

* The server pauses a session (`pause_reason`) when the connection drops (`CONNECTION_LOST`), the provider
  fails (`PROVIDER_ERROR`), the time limit is hit (`MAX_DURATION`) or a malformed frame arrives (`BAD_FRAME`).
  This cleanup is shielded from task cancellation. A session whose audio stopped arriving for 45 s is also
  flipped to PAUSED lazily on read.
* The app shows **RECORDING** only when the session is live AND the microphone is running AND the socket is
  open (`domain/recording.ts`, unit-tested). Otherwise it shows "NOT RECORDING" in words, not just colour.
* Withdrawing consent ends live sessions immediately; the gateway notices within one monitor interval
  (default 2 s) and closes with `4001 CONSENT_WITHDRAWN`.

## Gateway protocol

Control messages are JSON text, audio is binary. `client -> {"type":"auth","token":...}` (within 5 s; never in
the URL), `server -> {"type":"ready"}`, then frames of at most 64 KiB with an even length, and
`{"type":"stop"}` to end. Close codes: 4401 not authenticated, 4403 not allowed (including consent), 4404
unknown/not a participant, 4409 not active or already connected, 4001 ended/consent withdrawn, 4002 time limit,
4503 speech service unavailable, 1011 provider failure.

## Provider abstraction (`app/speech`)

`SpeechProvider` declares `SpeechCapabilities` (streaming, diarisation none/batch/stream, word timestamps,
code-mixed output, translation, languages) and implements `stream_transcribe`, `transcribe`, `detect_language`,
`identify_speakers`, `translate`. Unsupported calls raise `CapabilityNotSupported`; nothing is faked.
`SPEECH_PROVIDER` selects an adapter from the registry; `SPEECH_FALLBACK_PROVIDER` is used if the primary
raises. Audio consumed by a failed primary is not replayed: the gap is recorded in the usage row.
Registry rules: unknown names and *unbuilt* names (azure, google, deepgram, openai, bhashini) fail with
a precise message rather than a silent substitute; the **development provider is refused in production**.
The package imports nothing from the HTTP/database layers, so it can be extracted to its own service.

### What is stored per final segment
`seq`, `speaker_id` (provider label, e.g. `spk_0`, **never a role**), `start_ms`/`end_ms` (continuing across
pause/resume), `raw_text` (immutable), `normalised_text` (NULL until Phase 5; never replaces raw), `language`,
`secondary_language`, `language_confidence`, `confidence` (nullable: absent means "no claim"),
`code_switch_spans`, `provider`, `provider_model`. Partials are never stored. A database trigger makes segments
immutable.

### Speakers
Everyone starts as `UNKNOWN`. A person assigns `DOCTOR`, `PATIENT`, `FAMILY_MEMBER`, `OTHER_STAFF` or
`UNKNOWN` per speaker label (`PUT /interactions/{id}/speakers/{speaker_id}`, audited with before/after); the
change applies to the whole transcript. Speaker identity is never inferred from speaking order.

## Languages
`languages` is a table (BCP-47 tag, names, script, per-provider support). 13 are seeded (English, Hindi, Telugu,
Tamil, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi, Urdu, Odia, Assamese); adding one is a row.
Organisations can restrict the list. `provider_support` is empty until a provider has been *measured* for a
language, so the catalogue never over-claims. Code-switching is represented per segment (primary + secondary
language and character spans); the app displays "te-IN + en-IN" and flags low-confidence lines.

## Audio retention
Default: audio is **never stored** (processed in memory, discarded). Retention requires BOTH the organisation
policy `RETAIN_DAYS` and the patient's active `AUDIO_RETENTION` consent (which itself depends on
`AUDIO_RECORDING`). Retained audio is AES-256-GCM encrypted per chunk (dev: local files; production: object
storage, Phase 7). Deletion happens when the period ends or consent is withdrawn
(`python -m app.cli purge-audio`, to be scheduled); each deletion is audited. There is no endpoint to download
audio. Transcripts follow medical-record rules, not audio rules, and are not deleted by a withdrawal
(**legal review needed**).

## Cost and quality
`speech_usage` records, per session, provider/model, audio seconds, segments, first-segment latency, errors and
fallback. `estimated_cost_paise` stays NULL until a contract price exists. `GET /usage/speech` summarises it
(`usage:read`, administrators). `app/speech/eval.py` provides WER, CER, medical-term error rate, language-ID
accuracy and speaker-attribution accuracy (label-permutation invariant), independent of clinical-AI evaluation.
`app/speech/synthetic.py` holds invented English, Hindi+English, Telugu+English and Tamil+English scripts for
pipeline tests. **They were not reviewed by native speakers and must not be used to measure accuracy.** Real
evaluation needs reviewed, governed recordings and all ten target languages.

## Sarvam AI adapter (built, not yet run against the live service)
`app/speech/sarvam.py`, enabled by `AAROGYA_SPEECH_PROVIDER=sarvam` plus `AAROGYA_SARVAM_API_KEY`
(without a key, selecting it gives a precise "not configured" error). It was written from the **official
`sarvamai` Python SDK 0.1.37** (downloaded from PyPI and read first-hand), because the vendor's web docs host was
unreachable from the build environment. It targets the generally-available `wss://api.sarvam.ai/speech-to-text/ws`
endpoint (model `saaras:v4` by default), not the beta realtime one.

Protocol as implemented: `Api-Subscription-Key` header; query `language-code`, `model`, `mode`, `sample_rate`,
`input_audio_codec=pcm_s16le`, `vad_signals`, `flush_signal`; audio as base64 JSON messages; `{"type":"flush"}` at
the end of the audio, then a short wait for the last results (there is no end-of-stream message); replies of type
`data` / `events` / `error`.

What this endpoint does **not** give, so the adapter does not pretend to:
* **No speaker labels**: all speakers stay UNKNOWN until a person assigns roles (the existing rule).
* **No timestamps**: segment times are estimates (speech-start event position plus the vendor's reported audio
  duration), good to roughly the vendor's latency.
* **No confidence score** (`confidence` is None) and **no live partials** (final utterances only, found by the
  vendor's voice-activity detection; the "listening" preview will be empty with this provider).
* Translation, separate language detection and diarisation are not wired (`CapabilityNotSupported`).
Vendor error text is never propagated, only its code; the key is never logged or in any exception.

Tested: against a local fake server speaking the SDK protocol (message shapes, flush, error paths, cancellation)
and end to end through the gateway into stored transcripts. **Not tested: the real service.** Open questions only a
live run answers (use `services/api/scripts/sarvam_live_check.py`): whether raw PCM with
`input_audio_codec=pcm_s16le` is accepted exactly as sent, tail-of-audio behaviour after flush, latency from India,
accuracy on clinical and code-mixed speech (measure with `app.speech.eval` on reviewed recordings), rate/concurrency
limits for your plan, pricing, data retention/training terms, a data-processing agreement, and data residency.
Choose `AAROGYA_SARVAM_MODE` deliberately (`codemix` may suit English drug names inside Indic speech, `verbatim`
keeps spoken numbers un-normalised) and evaluate, do not assume.

## Mobile microphone capture
`MicrophoneCapture` (`apps/mobile/src/services/audio/capture.ts`) streams 16 kHz mono PCM16 through
`@siteed/audio-studio` **3.2.1 (pinned exactly)**, read from its published source. Privacy settings that matter:
* The library writes a WAV file by default; we turn that off (`output.primary.enabled: false`), so **audio is not
  kept on the phone**. A test locks this.
* The config plugin defaults enable notifications, background audio, Bluetooth/USB detection and the phone-state
  permission. All are disabled in `app.json`; `expo prebuild` confirms Android asks only for `RECORD_AUDIO` (plus
  internet, biometric, vibrate) and iOS has no background modes. Recording therefore works only while the
  consultation screen is in the foreground.
* If the OS takes the microphone (call, another app, device loss) the capture reports it, the indicator drops
  immediately, the session pauses on the server and the clinician sees why.
* Without the native module (Expo Go, web) it refuses with an explanation and the clinician documents manually.
Events come from the module's internal `AudioData` / `onRecordingInterrupted` emitter names (as read from 3.2.1),
which is why the version is pinned: re-verify them on every upgrade.
**Tested only against a fake backend and by `expo prebuild`; never run on a device.** Work through
`docs/DEVICE_TEST_PLAN.md` before clinical use. Development builds still use simulated audio unless
`EXPO_PUBLIC_USE_MICROPHONE=1`.

## Known limits
* The mobile app polls the transcript every second; SSE exists server-side for web/tablet clients.
* The "live partial" and the one-connection-per-session guard are per-process; running several API workers
  needs Redis (Phase 7).
* Manual correction of transcript *text* is not built; corrections will live in derived layers so the raw
  transcript is never altered.

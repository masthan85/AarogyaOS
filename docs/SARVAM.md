# Sarvam AI in AarogyaOS

Every Sarvam capability, what the app does with it, and how far it has been verified. **None of this has run
against the live service from this repository**: the build environment cannot reach `api.sarvam.ai`. Everything
is written against the official `sarvamai` SDK (and, for streaming speech, its WebSocket protocol) and tested
against local servers that speak the same wire format. Run the two live-check scripts with your key.

**Live result (16 Oct 2026, run by the owner on their own machine):** `sarvam_services_check.py` passed all three checks: translation en-IN to hi-IN (numbers preserved), text-to-speech (a WAV was produced) and chat (valid JSON returned). Still unchecked: how the speech sounds and whether the Hindi is clinically acceptable.

**Streaming speech-to-text, live (16 Oct 2026, owner's key and machine):** `sarvam_live_check.py` with a 9.8 s English test clip (16 kHz mono PCM) connected, accepted raw PCM, returned two final segments (START/END speech events, then a `data` message each) and the last segment arrived after the audio ended, so the flush works. Estimated times were produced as designed. A first run with a silent recording returned nothing and no error, which is expected. A second, 32.7 s clip of English mixed with spoken Hindi gave six segments, mostly accurate; one phrase came out wrong ("These two tablets two.") and the Hindi portion was written in Roman letters under the `en-IN` hint, so a transcript always needs a person to check it. Same clip with `auto` language: Hindi came back in Devanagari with a language tag per segment, but a short phrase scored only 0.498 for language. With `AAROGYA_SARVAM_MODE=codemix`: English words inside Hindi stay in Latin script (more readable for clinicians) and numbers in English come out as words, but the same short phrase was labelled Punjabi (0.663). So the app now lets Sarvam detect the language of each utterance and ignores the hint (`AAROGYA_SARVAM_USE_LANGUAGE_HINT=false`, the default; set it to true to use the patient's language as a hint instead). Consider `codemix` mode too, consider `codemix` mode, and trust nothing below about 0.75 language confidence: the app now marks those lines "please check". Not yet checked: accuracy beyond these two clips, Indian languages, code-mixed speech, drug names, noisy rooms, long sessions, reconnect behaviour, and the app's microphone path on a phone.

## What is used

| Sarvam capability | In the app | Code | Switch |
|---|---|---|---|
| **Speech-to-text, streaming** (`saaras:v4`) | Live consultation transcripts in 22 Indian languages and English; no speaker labels, no timestamps, final utterances only | `app/speech/sarvam.py` | `AAROGYA_SPEECH_PROVIDER=sarvam` |
| **Translation** (`sarvam-translate:v1`, formal, 22 languages) | Patient visit summary translated into the patient's language, as a **draft the doctor must read**; numbers compared with the English and flagged if they differ | `app/ai/sarvam.py`, `app/modules/summaries` | `AAROGYA_TRANSLATION_PROVIDER=sarvam` |
| **Text-to-speech** (`bulbul:v3`, 11 languages) | "Listen" on an **approved** summary or letter; audio is generated on request and never stored | same | `AAROGYA_TTS_PROVIDER=sarvam` |
| **Chat** (`sarvam-105b`) | An alternative model for clinical extraction, suggestions and chart questions, behind the same guardrails | same | `AAROGYA_LLM_PROVIDER=sarvam`, model in `AAROGYA_SARVAM_LLM_MODEL` |

One key serves all of them (the app reads `AAROGYA_SARVAM_API_KEY`; the two check scripts and `sarvam_hello.py` read `SARVAM_API_KEY`), but **nothing is sent to Sarvam unless its own switch is set**.
A key alone enables nothing (tested).

## What is deliberately not used

| Capability | Why not |
|---|---|
| **Voice cloning**, **dubbing** | No clinical use. Cloning a voice is an identity and consent hazard |
| **Batch speech-to-text with speaker labels** | Needs the recording kept (audio is discarded by default), a file-upload job flow, and the output format could not be verified without a live run. Worth adding once you can run it: it would give real speaker separation |
| **Document intelligence / document translation** | Would digitise scanned outside reports. Needs stored files and a review screen, and the job output format could not be verified. A good next feature, built against a live run |
| **Realtime streaming (beta)** and speech-to-text *translate* streaming | The generally-available endpoint is enough; translating speech silently would hide what was actually said |
| **Language identification** (text) | No screen needs it yet. The streaming transcript already reports the detected language |
| **Pronunciation dictionary** | Could improve drug-name pronunciation in speech output; needs a clinical word list we do not have |

## Safety rules that apply to every Sarvam call
- Patient text goes to Sarvam only with the organisation's AI switch **and** the patient's AI-processing consent (summaries,
  speech) or the recording's own consents (transcription). Checked on every call.
- Only doctor-approved text is spoken aloud. Translations are drafts until a doctor approves them; `NUMBERS_MISMATCH` is shown as a
  warning; digits are requested in international form (0-9) so a dose keeps its digits.
- Machine translation of medicine names and instructions can be wrong in ways a non-reader cannot see. Have a Hindi/Telugu/etc.
  reading clinician review translations before relying on them (CLINICAL_SAFETY H43).
- Vendor error text and the key are never put in exceptions, logs or audit rows; usage is metered (`/usage/ai`) without content.

## Checking it for real
```bash
cd services/api
python scripts/sarvam_services_check.py        # translation, text-to-speech and chat (uses made-up, non-clinical text)
python scripts/sarvam_live_check.py sample.wav hi-IN   # streaming speech-to-text with a 16 kHz mono WAV
```
Both read `SARVAM_API_KEY` from the environment or the git-ignored `.env`. Send me any failure text (never the key).

## Open questions only a live run answers
Whether raw PCM is accepted exactly as sent on the streaming endpoint; translation quality for medical text; whether `sarvam-105b`
follows the JSON schema reliably enough for extraction (compare with `python -m app.ai.eval`); latency from India; rate limits and
pricing for your plan; data retention, training use and residency terms; a signed data-processing agreement.

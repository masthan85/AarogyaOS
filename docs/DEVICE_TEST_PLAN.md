# Device test plan: microphone streaming and Sarvam speech-to-text

Neither the microphone module nor the Sarvam adapter has run on real hardware or against the real service.
This is the checklist that closes that gap. Use **synthetic or consented audio only**: it leaves the phone and
reaches the speech vendor.

## 0. Build
- `npx expo prebuild` then an EAS/dev build (Expo Go cannot load the native module and will say so).
- Set `EXPO_PUBLIC_USE_MICROPHONE=1` in a dev build (otherwise dev builds use simulated audio), and on the server
  `AAROGYA_SPEECH_PROVIDER=sarvam` + `AAROGYA_SARVAM_API_KEY`.
- Already verified by `expo prebuild` here: Android requests only `RECORD_AUDIO` (+ internet, biometric, vibrate);
  no storage, overlay, foreground-service, Bluetooth or phone-state permission; iOS has a microphone string and no
  background modes. Re-check after any dependency upgrade.

## 1. Sarvam alone (no phone): `services/api/scripts/sarvam_live_check.py`
| # | Check | Pass when |
|---|---|---|
| 1 | Connects with the key | no `refused the connection` |
| 2 | Raw PCM accepted as sent | text matches what was said (if garbled or rejected, a WAV container may be needed: report the vendor's message) |
| 3 | Tail of audio | speech in the last seconds before stopping still appears (flush works) |
| 4 | Auto-detect and each target language | `language` correct; try Hindi, Telugu, Tamil, Indian English |
| 5 | Code-mixed speech and drug names | measure word error rate with `app.speech.eval` on reviewed recordings; try `AAROGYA_SARVAM_MODE=codemix` |
| 6 | Latency | segment appears within an acceptable time of the speaker finishing |
| 7 | Limits | concurrent sessions and rate limits for your plan |

## 2. Microphone on devices (a low-end and a recent Android; an iPhone)
| # | Check | Pass when |
|---|---|---|
| 1 | Permission prompt: allow / deny / "don't ask again" | deny gives the plain message, nothing records, manual documentation continues |
| 2 | Start / Stop | indicator says RECORDING only while audio flows; Stop ends it immediately |
| 3 | Audio format | server receives 16 kHz mono PCM16 (gateway rejects malformed frames); try a Bluetooth headset |
| 4 | **No audio left on the phone** | after a session, no recording file exists in the app's storage (inspect with adb / Files) |
| 5 | Incoming call mid-recording | session pauses itself, banner explains, resumes after the call |
| 6 | Another app takes the mic (voice note, video call) | same |
| 7 | Screen lock / app to background | recording stops and the session pauses (background capture is deliberately off); no silent recording |
| 8 | Network drop and return | session pauses on drop; resume continues the transcript without duplicates |
| 9 | 30 and 60 minute sessions | no crash, battery and heat acceptable, memory stable |
| 10 | Noisy clinic recording | transcript quality understood; compare with a quiet room |
| 11 | Wrong-patient safety | the header, recording bar and consent state match the patient actually in the room |

## 3. Accept for pilot only if
Every row passes on each device class you will use, the Sarvam word error rate on reviewed clinical recordings
is acceptable to the clinical lead, and the findings are recorded in the clinical-safety log.

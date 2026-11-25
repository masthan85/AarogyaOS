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

## Layout on phones and tablets

The layout was checked in a browser at phone and tablet sizes (`DESIGN_REVIEW.md`, sixth pass). These need a device, on at least one small Android phone, one iPhone with a notch, one Android tablet and one iPad:

| Check | Expected |
|---|---|
| Open the app on an iPad | It fills the screen; it is not a scaled-up phone app |
| Hold a tablet on its side | The sidebar appears and nothing sits under the status bar or the home indicator |
| Turn the tablet upright, then back | The layout switches between phone and sidebar form without losing what was typed |
| Open a consultation on a tablet on its side | The record and the patient panel sit side by side |
| Tap the last field on a long form (new patient, triage, prescription) | The field stays visible above the keyboard, on iOS and on Android |
| With the keyboard open, tap a button | It works on the first tap |
| Stop the server while signed in | The connection banner is fully visible below the status bar |
| Set the system font to its largest size | Text wraps; nothing is cut off and every button can still be reached |
| Put the app beside another app in split view on an iPad | It uses the phone layout and stays usable |
| Use a tablet with a hardware keyboard | Tab moves between fields in order |
| With screen protection on (Organisation settings), take a screenshot on Android | It is refused, and the app is blank in the recent-apps view |
| Start a screen recording on an iPhone or iPad | The app shows blank in the recording |
| Scan the two-step sign-in QR code with Google Authenticator and Microsoft Authenticator | The account is added and its codes are accepted |


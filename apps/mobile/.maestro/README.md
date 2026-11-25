# Native app flows (Maestro)

Smoke flows for the Android and iOS app, matching the browser tests in `e2e/`: each demo role signs
in, sees its own sections and not another role's, and opens its main screen without an error; a wrong
password is refused.

**Status: running in CI** in the `android-maestro` job: a release build on an Android 14 emulator
(Pixel 6 profile) against a real API with the demo clinic, about 22 minutes, in parallel with the
other jobs. `run-ci.sh` runs each flow separately and prints the screen's elements when one fails,
so a failure can be read from the log. The flows have not run on iOS or on a physical device yet.

Notes from making them pass, which also apply to anyone writing new flows:

- Find inputs and buttons by test id (`login-organisation`, `sign-in`). Tapping a field's visible
  label does not move focus, and "Sign in" is both a heading and a button.
- An open keyboard covers the lower fields. Move on with the keyboard's Next key, as a person would.
- On a phone, some sections are panels on the home screen rather than tiles (the queue is "Open
  queue"), so check for what the phone actually shows.

To run them:

1. Start the API with the demo clinic (`python -m app.cli demo-seed`), reachable from the device.
2. Build and install a development build with `EXPO_PUBLIC_API_URL` pointing at that API
   (`npx expo run:android` or `npx expo run:ios`). Expo Go uses a different app id and will not work.
3. Install Maestro (https://maestro.mobile.dev) and, from `apps/mobile`, run `maestro test .maestro`.

Demo accounts and invented patients only; never point these flows at a clinic with real patients.

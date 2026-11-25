# Native app flows (Maestro)

Smoke flows for the Android and iOS app, matching the browser tests in `e2e/`: each demo role signs
in, sees its own sections and not another role's, and opens its main screen without an error; a wrong
password is refused.

**Status: written, not yet run on a device or emulator.** Expect to adjust labels or waits the first
time they run. They become a CI job once a device farm (or an emulator runner) is chosen.

To run them:

1. Start the API with the demo clinic (`python -m app.cli demo-seed`), reachable from the device.
2. Build and install a development build with `EXPO_PUBLIC_API_URL` pointing at that API
   (`npx expo run:android` or `npx expo run:ios`). Expo Go uses a different app id and will not work.
3. Install Maestro (https://maestro.mobile.dev) and, from `apps/mobile`, run `maestro test .maestro`.

Demo accounts and invented patients only; never point these flows at a clinic with real patients.

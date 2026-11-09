# AarogyaOS mobile app

The Expo and React Native client for AarogyaOS. It talks only to the AarogyaOS API and holds no vendor keys. Product context is in the repository `README.md`; this file covers working in the app.

## Run

```bash
npm install
EXPO_PUBLIC_API_URL=http://10.0.2.2:8000 npx expo start
```

`10.0.2.2` is how an Android emulator reaches the host machine; use the computer's network address for a phone. Set `EXPO_PUBLIC_USE_MICROPHONE=1` in a development or release build to use the real microphone (Expo Go cannot); otherwise a scripted sample conversation is used. Anything named `EXPO_PUBLIC_*` is compiled into the app.

## Check

```bash
npm run typecheck
npm test
CI=1 npx expo export --platform android --output-dir /tmp/export
```

## Layout

`src/app` routes (Expo Router), `src/features` screens by area, `src/domain` pure logic with tests, `src/api` typed client with zod schemas, `src/design-system` tokens and components, `src/services` device services (secure token store, biometrics, printing, audio capture). Expo SDK 58 is installed; `AGENTS.md` asks contributors to check the SDK documentation before using an Expo API.

Setup details are in `docs/05-INSTALLATION-SETUP.md`, conventions in `docs/09-DEVELOPMENT-GUIDE.md` and configuration in `docs/06-CONFIGURATION.md`.

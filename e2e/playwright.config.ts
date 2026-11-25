import { defineConfig, devices } from '@playwright/test';

/**
 * Browser tests against the web build of the app. They expect the API and the web app to be
 * running already, with the demo clinic loaded (docs/05-INSTALLATION-SETUP.md):
 *
 *   API:  python -m uvicorn app.main:create_app --factory --port 8000
 *   App:  EXPO_PUBLIC_API_URL=http://localhost:8000 npx expo start --web --port 8081
 *   or the production build, as CI does:
 *         EXPO_PUBLIC_API_URL=http://localhost:8000 npx expo export -p web --output-dir ../../e2e/web
 *         node serve-web.mjs web 8081   (from e2e/)
 *
 * E2E_BASE_URL points them at another address. Use the demo clinic only: never a clinic with real
 * patients.
 */
export default defineConfig({
  testDir: './tests',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8081',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } } },
    { name: 'phone', use: { ...devices['Pixel 7'] } },
  ],
});

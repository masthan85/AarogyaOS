import { expect, test } from '@playwright/test';

/**
 * Seed for the Playwright test agents: the state every generated test starts from. It signs in to
 * the demo clinic as the doctor and waits for the home screen. Tests for another role can copy this
 * and change the email (admin, reception, nurse, pharmacist, lab, billing @demo.example.com).
 *
 * Demo accounts only. The password is the published demo password, not a secret.
 */
const ORGANISATION = process.env.E2E_ORGANISATION ?? 'demo-clinic';
const EMAIL = process.env.E2E_EMAIL ?? 'doctor@demo.example.com';
const PASSWORD = process.env.E2E_PASSWORD ?? 'Demo-pass-2026!';

test.describe('AarogyaOS', () => {
  test('seed', async ({ page }) => {
    await page.goto('/');
    await page.getByLabel('Organisation').fill(ORGANISATION);
    await page.getByLabel('Email').fill(EMAIL);
    await page.getByLabel('Password', { exact: true }).fill(PASSWORD);
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByText('Today at a glance').or(page.getByText('The day at the clinic')).first()).toBeVisible();
  });
});

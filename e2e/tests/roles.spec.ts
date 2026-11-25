import { expect, test } from '@playwright/test';

import { expectNoFailures, HOME, type Role, signIn, watchApi } from './support';

/**
 * Smoke test per role, against the demo clinic: each person signs in, sees only the sections their
 * role allows, and their main screen loads without a refused or failed request.
 */
const ROLES: { who: Role; sees: string[]; never: string[]; open: string }[] = [
  { who: 'doctor', sees: ['Queue', 'Patients', 'Results to review'], never: ['Billing', 'Administration'], open: 'Queue' },
  { who: 'nurse', sees: ['Queue', 'Patients'], never: ['Results to review', 'Billing', 'Administration'], open: 'Queue' },
  { who: 'reception', sees: ['Queue', 'Appointments', 'Billing'], never: ['Results to review', 'Pharmacy', 'Administration'], open: 'Appointments' },
  { who: 'pharmacist', sees: ['Pharmacy'], never: ['Queue', 'Billing', 'Administration'], open: 'Pharmacy' },
  { who: 'lab', sees: ['Orders and results'], never: ['Queue', 'Billing', 'Pharmacy'], open: 'Orders and results' },
  { who: 'billing', sees: ['Billing'], never: ['Queue', 'Results to review', 'Pharmacy', 'Administration'], open: 'Billing' },
  // A clinic administrator configures the clinic and cannot open patient records.
  { who: 'admin', sees: ['Administration', 'Facilities'], never: ['Patients', 'Queue'], open: 'Administration' },
];

test.describe('each role', () => {
  test.skip(({ isMobile }) => isMobile, 'The sidebar is shown on wide screens; phones are covered below.');

  for (const role of ROLES) {
    test(`${role.who} sees their own sections and can open ${role.open}`, async ({ page }) => {
      const failed = watchApi(page);
      await signIn(page, role.who);
      await expect(page.getByText(HOME).first()).toBeVisible();
      const nav = page.getByRole('navigation');
      for (const name of role.sees) await expect(nav.getByRole('link', { name, exact: true })).toBeVisible();
      for (const name of role.never) await expect(nav.getByRole('link', { name, exact: true })).toHaveCount(0);

      await nav.getByRole('link', { name: role.open, exact: true }).click();
      await expect(nav.getByRole('link', { name: role.open, exact: true })).toHaveAttribute('aria-current', 'page');
      await page.waitForLoadState('networkidle');
      await expectNoFailures(page, failed);
    });
  }
});

test('every role reaches the home screen on a phone', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'Phone layout only.');
  for (const role of ROLES) {
    const failed = watchApi(page);
    await page.context().clearCookies();
    await page.goto('/');
    await page.evaluate(() => window.localStorage.clear());
    await signIn(page, role.who);
    await expect(page.getByText(HOME).first()).toBeVisible();
    await page.waitForLoadState('networkidle');
    await expectNoFailures(page, failed);
  }
});

test('a wrong password is refused with a plain message', async ({ page }) => {
  await signIn(page, 'doctor', 'not-the-password');
  await expect(page.getByText('Email, password or organisation is incorrect.')).toBeVisible();
  await expect(page.getByText(HOME)).toHaveCount(0);
});

test('signing out returns to the sign-in screen', async ({ page, isMobile }) => {
  test.skip(isMobile, 'Sign out is in the sidebar on wide screens.');
  await signIn(page, 'nurse');
  await expect(page.getByText(HOME).first()).toBeVisible();
  await page.getByRole('navigation').getByRole('link', { name: 'Sign out' }).click();
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible();
});

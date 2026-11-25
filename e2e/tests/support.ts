import { expect, type Page, type Response } from '@playwright/test';

/** Demo accounts only: the password is the published demo password, not a secret. */
export const ORGANISATION = process.env.E2E_ORGANISATION ?? 'demo-clinic';
export const PASSWORD = process.env.E2E_PASSWORD ?? 'Demo-pass-2026!';
export const HOME = /Today at a glance|The day at the clinic/;

export type Role = 'admin' | 'doctor' | 'nurse' | 'reception' | 'pharmacist' | 'lab' | 'billing';

export async function signIn(page: Page, who: Role | string, password = PASSWORD) {
  const email = who.includes('@') ? who : `${who}@demo.example.com`;
  await page.goto('/');
  await page.getByLabel('Organisation', { exact: true }).fill(ORGANISATION);
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
}

/** Records every API answer that was refused or failed, so a screen that quietly breaks is caught. */
export function watchApi(page: Page): Response[] {
  const failed: Response[] = [];
  page.on('response', (r) => {
    if (r.request().resourceType() !== 'fetch' && r.request().resourceType() !== 'xhr') return;
    if (r.status() >= 400) failed.push(r);
  });
  return failed;
}

export async function expectNoFailures(page: Page, failed: Response[]) {
  await expect(page.getByText(/^Could not load/)).toHaveCount(0);
  expect(failed.map((r) => `${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}`)).toEqual([]);
}

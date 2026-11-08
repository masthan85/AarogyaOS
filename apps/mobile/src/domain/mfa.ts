import { ApiError } from '@/api/client';

/** The server asks for a second factor with a 401 whose error title is `mfa_required`. */
export function needsSecondFactor(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401 && err.body?.title === 'mfa_required';
}

export function wrongSecondFactor(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401 && err.body?.title === 'invalid_mfa_code';
}

/** Tidies what a person typed: authenticator codes may be pasted as "123 456"; recovery codes keep their dash. */
export function tidyCode(input: string): string {
  const t = input.trim();
  if (/^[0-9 ]+$/.test(t)) return t.replace(/\s+/g, '');
  return t.toLowerCase();
}

export function looksLikeCode(input: string): boolean {
  const t = tidyCode(input);
  return /^\d{6}$/.test(t) || /^[0-9a-f]{5}-?[0-9a-f]{5}$/.test(t);
}

/** Groups the secret in fours so it is easier to type into an authenticator app. */
export function groupSecret(secret: string): string {
  return secret.replace(/(.{4})/g, '$1 ').trim();
}

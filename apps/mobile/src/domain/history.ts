/** Small rules for the procedures, vaccines and referrals screens. */

/** Accepts 2026-11-04 or 04/11/2026 (the way dates are written in India) and returns ISO, or null. */
export function parseDate(input: string, today: Date = new Date()): string | null {
  const text = input.trim();
  let y: number, m: number, d: number;
  const iso = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(text);
  const dmy = /^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/.exec(text);
  if (iso) [y, m, d] = [Number(iso[1]), Number(iso[2]), Number(iso[3])];
  else if (dmy) [d, m, y] = [Number(dmy[1]), Number(dmy[2]), Number(dmy[3])];
  else return null;
  const date = new Date(Date.UTC(y, m - 1, d));
  if (date.getUTCFullYear() !== y || date.getUTCMonth() !== m - 1 || date.getUTCDate() !== d) return null;
  return `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

export function isoToday(today: Date = new Date()): string {
  return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
}

/** True when a past-date field holds a date that is not after today. */
export function notFuture(iso: string, today: Date = new Date()): boolean {
  return iso <= isoToday(today);
}

export const REFERRAL_STEPS: Record<string, string[]> = {
  REQUESTED: ['ACCEPTED', 'DECLINED', 'CANCELLED', 'COMPLETED'],
  ACCEPTED: ['COMPLETED', 'CANCELLED'],
  COMPLETED: [],
  DECLINED: [],
  CANCELLED: [],
};

export const REFERRAL_LABELS: Record<string, string> = {
  REQUESTED: 'Requested',
  ACCEPTED: 'Accepted',
  COMPLETED: 'Seen',
  DECLINED: 'Declined',
  CANCELLED: 'Cancelled',
};

export function nextReferralStates(status: string): string[] {
  return REFERRAL_STEPS[status] ?? [];
}

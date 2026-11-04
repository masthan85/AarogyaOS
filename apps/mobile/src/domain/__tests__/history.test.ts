import { isoToday, nextReferralStates, notFuture, parseDate } from '../history';

describe('parseDate', () => {
  it('reads ISO and day-first dates', () => {
    expect(parseDate('2026-11-04')).toBe('2026-11-04');
    expect(parseDate('4/11/2026')).toBe('2026-11-04');
    expect(parseDate('04-11-2026')).toBe('2026-11-04');
  });
  it('rejects impossible dates', () => {
    expect(parseDate('31/02/2026')).toBeNull();
    expect(parseDate('yesterday')).toBeNull();
    expect(parseDate('')).toBeNull();
  });
});

describe('notFuture', () => {
  const today = new Date(2026, 10, 4);
  it('allows today and earlier only', () => {
    expect(isoToday(today)).toBe('2026-11-04');
    expect(notFuture('2026-11-04', today)).toBe(true);
    expect(notFuture('2026-11-05', today)).toBe(false);
  });
});

describe('nextReferralStates', () => {
  it('lets open referrals move on and closed ones stop', () => {
    expect(nextReferralStates('REQUESTED')).toContain('ACCEPTED');
    expect(nextReferralStates('ACCEPTED')).toEqual(['COMPLETED', 'CANCELLED']);
    expect(nextReferralStates('COMPLETED')).toEqual([]);
    expect(nextReferralStates('unknown')).toEqual([]);
  });
});

import { formatDate } from '../dates';

describe('formatDate', () => {
  it('shows a date-only value without a timezone shift', () => {
    expect(formatDate('2026-11-04')).toMatch(/4 Nov 2026/);
    expect(formatDate('nonsense')).toBe('nonsense');
  });
});

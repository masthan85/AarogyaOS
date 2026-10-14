import { addDays, toDateString } from '../dates';
import { eventLabel } from '../events';
import { normaliseIndianMobile } from '../phone';

describe('normaliseIndianMobile (mirrors the server rules)', () => {
  it.each(['9876543210', '+91 98765 43210', '09876543210', '0091-98765-43210', '91 9876543210'])(
    'accepts %s',
    (raw) => expect(normaliseIndianMobile(raw)).toBe('+919876543210'),
  );
  it.each(['12345', '5876543210', '98765432100', 'abc', ''])('rejects %s', (raw) =>
    expect(normaliseIndianMobile(raw)).toBeNull(),
  );
});

describe('dates', () => {
  it('formats local calendar dates with zero padding', () => {
    expect(toDateString(new Date(2026, 0, 5))).toBe('2026-01-05');
  });
  it('adds days across month boundaries without mutating the input', () => {
    const d = new Date(2026, 0, 31);
    expect(toDateString(addDays(d, 1))).toBe('2026-02-01');
    expect(toDateString(d)).toBe('2026-01-31');
  });
});

describe('eventLabel', () => {
  it('uses friendly labels and falls back to a readable form', () => {
    expect(eventLabel('PATIENT_CHECKED_IN')).toBe('Checked in');
    expect(eventLabel('SOMETHING_NEW')).toBe('Something new');
  });
});

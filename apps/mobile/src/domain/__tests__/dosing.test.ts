import { parseFrequency } from '../dosing';

describe('parseFrequency', () => {
  it('reads the usual morning-afternoon-night notation', () => {
    expect(parseFrequency('1-0-1')).toEqual({ text: 'twice daily: morning and night', timesPerDay: 2, changesDose: false });
    expect(parseFrequency('1-1-1')?.text).toBe('three times daily: morning and afternoon and night');
    expect(parseFrequency('0-0-1')).toEqual({ text: 'once daily: night', timesPerDay: 1, changesDose: false });
    expect(parseFrequency('1 - 0 - 0 - 1')?.text).toBe('twice daily: morning and night');
    expect(parseFrequency('1-0-1-1')?.timesPerDay).toBe(3);
  });
  it('flags notation that changes the amount at each time, and never hides the amounts', () => {
    const r = parseFrequency('2-0-1');
    expect(r?.changesDose).toBe(true);
    expect(r?.text).toBe('twice daily: 2 in the morning, 1 in the night');
    expect(parseFrequency('½-0-½')?.text).toBe('twice daily: ½ in the morning, ½ in the night');
    expect(parseFrequency('1/2-0-1/2')?.changesDose).toBe(true);
  });
  it('reads the standard abbreviations with an optional meal word', () => {
    expect(parseFrequency('bd')?.text).toBe('twice daily');
    expect(parseFrequency('TDS PC')?.text).toBe('three times daily, after food');
    expect(parseFrequency('1-0-1 AC')?.text).toBe('twice daily: morning and night, before food');
    expect(parseFrequency('HS')?.text).toBe('at bedtime');
    expect(parseFrequency('SOS')?.timesPerDay).toBeNull();
  });
  it('does not guess at anything else', () => {
    for (const s of ['', 'twice a day', 'subah sham', '0-0-0', '1-x-1', 'BD XYZ', '1-0', 'OD BD', '5']) {
      expect(parseFrequency(s)).toBeNull();
    }
  });
});

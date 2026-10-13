import { formatVital, interpretationLabel, interpretationTone, needsVerification, parseNumber, provenance } from '../clinical';

describe('provenance wording keeps humans and AI visibly distinct', () => {
  it('flags unverified staff entries', () => {
    expect(provenance('STAFF_ENTERED', 'UNVERIFIED')).toEqual({ text: 'Staff · unverified', tone: 'warning' });
  });
  it('shows clinician confirmation', () => {
    expect(provenance('PATIENT_REPORTED', 'CLINICIAN_CONFIRMED')).toEqual({ text: 'Patient said · confirmed', tone: 'success' });
  });
  it('gives AI output its own tone while it awaits review', () => {
    expect(provenance('AI_EXTRACTED', 'AI_GENERATED')).toEqual({ text: 'AI · needs review', tone: 'ai' });
  });
  it('marks rejected facts as such', () => {
    expect(provenance('DOCTOR_ENTERED', 'CLINICIAN_REJECTED').tone).toBe('danger');
  });
  it('knows which states still need a clinician', () => {
    expect(needsVerification('UNVERIFIED')).toBe(true);
    expect(needsVerification('CLINICIAN_CONFIRMED')).toBe(false);
  });
});

describe('interpretation', () => {
  it('maps severity to tone', () => {
    expect(interpretationTone('CRITICAL_HIGH')).toBe('danger');
    expect(interpretationTone('HIGH')).toBe('warning');
    expect(interpretationTone('NORMAL')).toBe('success');
    expect(interpretationTone('UNKNOWN')).toBe('neutral');
  });
  it('says nothing when there is no reference range, rather than implying normal', () => {
    expect(interpretationLabel('UNKNOWN')).toBeNull();
    expect(interpretationLabel('NOT_APPLICABLE')).toBeNull();
    expect(interpretationLabel('CRITICAL_LOW')).toBe('Critically low');
  });
});

describe('vitals formatting and parsing', () => {
  it('shows what was originally entered when converted', () => {
    expect(formatVital({ value: 38.61, unit: '°C', original_value: 101.5, original_unit: '°F' })).toBe('38.6 °C (entered 101.5 °F)');
    expect(formatVital({ value: 80, unit: 'bpm', original_value: null, original_unit: null })).toBe('80 bpm');
  });
  it('parses numbers and flags junk', () => {
    expect(parseNumber('  ')).toBeUndefined();
    expect(parseNumber('98.6')).toBe(98.6);
    expect(Number.isNaN(parseNumber('abc'))).toBe(true);
  });
});

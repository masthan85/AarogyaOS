import type { KnowledgeDoc, OrgPolicy } from '@/api/schemas';

import { allowanceLine, approvalState, describeHours, emailProblem, hoursFor, parseAllowance, passwordProblem, policyProblem, splitPassages, timeProblem, togglePolicy } from '../admin';

const policy: OrgPolicy = {
  recording_enabled: true, ai_processing_enabled: true, audio_retention: 'RETAIN_DAYS', retain_days: 30,
  ai_suggestions_enabled: true, ai_suggestions_require_source: true, enabled_languages: null, guardian_consent_under_age: 18,
  monthly_speech_minutes_limit: null, monthly_ai_calls_limit: null, usage_alert_percent: 80,
};
const doc = (o: Partial<KnowledgeDoc>): KnowledgeDoc => ({
  id: 'd', title: 't', publisher: 'p', source: 's', version: '1', country: 'IN', specialty: null, licence: 'ORG_LICENSED',
  approved: false, retired_at: null, created_by: 'u1', chunk_count: 1, ...o,
});

describe('organisation switches', () => {
  it('turning recording off also stops audio being kept', () => {
    const next = togglePolicy(policy, 'recording_enabled', false);
    expect(next.audio_retention).toBe('DISCARD_AFTER_TRANSCRIPTION');
    expect(policyProblem(next)).toBeNull();
  });
  it('turning AI off also turns suggestions off', () => {
    const next = togglePolicy(policy, 'ai_processing_enabled', false);
    expect(next.ai_suggestions_enabled).toBe(false);
    expect(policyProblem(next)).toBeNull();
  });
  it('names a combination the server would refuse', () => {
    expect(policyProblem({ ...policy, ai_processing_enabled: false })).toMatch(/AI processing/);
    expect(policyProblem({ ...policy, recording_enabled: false })).toMatch(/recording is off/);
    expect(policyProblem({ ...policy, retain_days: 0 })).toMatch(/days/);
  });
});

describe('form checks', () => {
  it('checks passwords and emails', () => {
    expect(passwordProblem('short')).toMatch(/12/);
    expect(passwordProblem('a-long-enough-password')).toBeNull();
    expect(emailProblem('nope')).not.toBeNull();
    expect(emailProblem(' dr@clinic.example.com ')).toBeNull();
  });
  it('splits reference text into passages on blank lines and drops empties', () => {
    expect(splitPassages('First  passage\nstill first.\n\n\n  Second one.  \n\n')).toEqual(['First passage still first.', 'Second one.']);
    expect(splitPassages('   ')).toEqual([]);
  });
});

describe('reference documents', () => {
  it('only someone else can approve, and approved or retired ones cannot be approved again', () => {
    expect(approvalState(doc({}), 'u1')).toBe('own');
    expect(approvalState(doc({}), 'u2')).toBe('ready');
    expect(approvalState(doc({ approved: true }), 'u2')).toBe('approved');
    expect(approvalState(doc({ approved: true, retired_at: '2026-01-01' }), 'u2')).toBe('retired');
  });
});

describe('working hours', () => {
  it('validates times and builds the weekly list', () => {
    expect(timeProblem('9:00', '17:00')).toMatch(/HH:MM/);
    expect(timeProblem('17:00', '09:00')).toMatch(/before/);
    expect(timeProblem('09:00', '17:00')).toBeNull();
    const hours = hoursFor([4, 0, 1], '09:00', '13:30');
    expect(hours.map((h) => h.weekday)).toEqual([0, 1, 4]);
    expect(hours[0]).toEqual({ weekday: 0, start_time: '09:00:00', end_time: '13:30:00' });
    expect(describeHours(hours)).toBe('Mon 09:00-13:30, Tue 09:00-13:30, Fri 09:00-13:30');
    expect(describeHours([])).toMatch(/cannot be booked/);
  });
});

describe('allowances', () => {
  it('reads an empty box as no limit and refuses anything that is not a whole number', () => {
    expect(parseAllowance('')).toBeNull();
    expect(parseAllowance('  ')).toBeNull();
    expect(parseAllowance('0')).toBe(0);
    expect(parseAllowance(' 600 ')).toBe(600);
    expect(parseAllowance('-5')).toBeUndefined();
    expect(parseAllowance('12.5')).toBeUndefined();
    expect(parseAllowance('lots')).toBeUndefined();
  });

  it('says where an allowance stands in plain words', () => {
    expect(allowanceLine({ used: 12, limit: null, state: 'UNLIMITED' }, 'speech minutes')).toBe('12 speech minutes used this month. No limit set.');
    expect(allowanceLine({ used: 90, limit: 100, state: 'NEAR' }, 'AI requests')).toContain('Close to the allowance');
    expect(allowanceLine({ used: 100, limit: 100, state: 'REACHED' }, 'AI requests')).toContain('switched off until next month');
  });
});

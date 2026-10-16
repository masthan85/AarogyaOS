import type { ReportedResult, WorklistFollowUp } from '@/api/schemas';

import { buildResult, dispenseState, coverProblem, byPriority, describeValue, emptyResultForm, groupFollowUps, isCritical, reviewOrder } from '../worklists';

const form = (o: Partial<ReturnType<typeof emptyResultForm>>) => ({ ...emptyResultForm('Haemoglobin'), ...o });
const res = (o: Partial<ReportedResult>): ReportedResult => ({
  id: 'r', patient_id: 'p', service_request_id: 's', test_name: 'Hb', value_numeric: 9, value_text: null, unit: 'g/dL',
  ref_low: 12, ref_high: 16, interpretation: 'LOW', comment: null, reported_at: '2026-01-01T10:00:00Z', reviewed_at: null, ...o,
});
const fu = (id: string, due: string): WorklistFollowUp => ({
  id, patient_id: 'p', encounter_id: 'e', due_date: due, kind: 'REVIEW', reason: 'r', status: 'PENDING',
});

describe('buildResult', () => {
  it('sends a plain number as a number with its ranges', () => {
    const r = buildResult(form({ value: '9.5', unit: 'g/dL', refLow: '12', refHigh: '16', criticalLow: '7' }));
    expect(r.body).toEqual({ test_name: 'Haemoglobin', value_numeric: 9.5, unit: 'g/dL', ref_low: 12, ref_high: 16, critical_low: 7 });
  });
  it('keeps non-numeric results as text', () => {
    expect(buildResult(form({ value: 'Positive' })).body).toEqual({ test_name: 'Haemoglobin', value_text: 'Positive' });
  });
  it('asks for the missing pieces', () => {
    expect(buildResult(form({ testName: ' ', value: '1' })).error).toMatch(/test name/);
    expect(buildResult(form({ value: '' })).error).toMatch(/result/);
  });
  it('refuses a malformed or contradictory range', () => {
    expect(buildResult(form({ value: '9', refLow: 'abc' })).error).toMatch(/number/);
    expect(buildResult(form({ value: '9', refLow: '16', refHigh: '12' })).error).toMatch(/above/);
    expect(buildResult(form({ value: '9', criticalLow: '9', criticalHigh: '3' })).error).toMatch(/critical/);
  });
  it('refuses ranges on a text result', () => {
    expect(buildResult(form({ value: 'Positive', refLow: '1' })).error).toMatch(/numeric/);
  });
});

describe('ordering', () => {
  it('puts urgent orders first and keeps unknown priorities last', () => {
    const rows = byPriority([{ priority: 'ROUTINE' }, { priority: 'X' }, { priority: 'URGENT' }, { priority: 'STAT' }]);
    expect(rows.map((r) => r.priority)).toEqual(['STAT', 'URGENT', 'ROUTINE', 'X']);
  });
  it('reviews critical results before normal ones, oldest first within a group', () => {
    const rows = reviewOrder([
      res({ id: 'n', interpretation: 'NORMAL' }),
      res({ id: 'c2', interpretation: 'CRITICAL_LOW', reported_at: '2026-01-02T00:00:00Z' }),
      res({ id: 'c1', interpretation: 'CRITICAL_HIGH', reported_at: '2026-01-01T00:00:00Z' }),
    ]);
    expect(rows.map((r) => r.id)).toEqual(['c1', 'c2', 'n']);
  });
});

describe('result wording', () => {
  it('shows value, unit and range', () => {
    expect(describeValue(res({}))).toBe('9 g/dL (normal 12–16)');
    expect(describeValue(res({ value_numeric: null, value_text: 'Positive', unit: null, ref_low: null, ref_high: null }))).toBe('Positive');
  });
  it('recognises critical results', () => {
    expect(isCritical(res({ interpretation: 'CRITICAL_LOW' }))).toBe(true);
    expect(isCritical(res({ interpretation: 'LOW' }))).toBe(false);
  });
});

describe('groupFollowUps', () => {
  it('groups by due date and drops empty groups', () => {
    const g = groupFollowUps([fu('a', '2026-03-10'), fu('b', '2026-03-01'), fu('c', '2026-03-05'), fu('d', '2026-03-20')], '2026-03-05', '2026-03-11');
    expect(g.map((x) => [x.key, x.rows.map((r) => r.id)])).toEqual([
      ['overdue', ['b']], ['today', ['c']], ['week', ['a']], ['later', ['d']],
    ]);
    expect(groupFollowUps([], '2026-03-05', '2026-03-11')).toEqual([]);
  });
});

describe('coverProblem', () => {
  it('accepts a short window and names what is wrong otherwise', () => {
    expect(coverProblem('2026-03-05', '2026-03-08', '2026-03-05')).toBeNull();
    expect(coverProblem('2026-03-05', '2026-03-01', '2026-03-05')).toMatch(/before/);
    expect(coverProblem('2026-01-01', '2026-01-03', '2026-03-05')).toMatch(/already ended/);
    expect(coverProblem('2026-03-05', '2026-05-05', '2026-03-05')).toMatch(/at most/);
    expect(coverProblem('5 March', '2026-03-08', '2026-03-05')).toMatch(/YYYY/);
  });
});

describe('dispenseState', () => {
  it('follows the newest record and treats full dispensing as final', () => {
    expect(dispenseState([])).toEqual({ label: 'Not dispensed yet', tone: 'neutral', canRecord: true });
    const history = [
      { status: 'PARTIALLY_DISPENSED', created_at: '2026-03-01T10:00:00Z' },
      { status: 'DISPENSED', created_at: '2026-03-02T10:00:00Z' },
    ];
    expect(dispenseState(history).canRecord).toBe(false);
    expect(dispenseState([history[0]]).label).toBe('Partly dispensed');
    expect(dispenseState([{ status: 'NOT_DISPENSED', created_at: 'x' }]).canRecord).toBe(true);
  });
});

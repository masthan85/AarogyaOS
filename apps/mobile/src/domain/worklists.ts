import type { ReportedResult, WorklistFollowUp } from '@/api/schemas';
import type { ResultInput } from '@/api/endpoints';

export type ResultForm = {
  testName: string;
  value: string;
  unit: string;
  refLow: string;
  refHigh: string;
  criticalLow: string;
  criticalHigh: string;
  comment: string;
};

export const emptyResultForm = (testName: string): ResultForm => ({
  testName, value: '', unit: '', refLow: '', refHigh: '', criticalLow: '', criticalHigh: '', comment: '',
});

const NUMBER = /^-?\d+(\.\d+)?$/;
const optionalNumber = (raw: string, label: string): { n?: number; error?: string } => {
  const v = raw.trim();
  if (!v) return {};
  if (!NUMBER.test(v)) return { error: `${label} must be a number.` };
  return { n: Number(v) };
};

/**
 * Turns what the technician typed into the request, or says what is wrong. A value that is a plain number goes
 * in as a number (so the server can flag it against the ranges); anything else is kept as the text typed.
 */
export function buildResult(form: ResultForm): { body?: ResultInput; error?: string } {
  const name = form.testName.trim();
  if (!name) return { error: 'Enter the test name.' };
  const value = form.value.trim();
  if (!value) return { error: 'Enter the result.' };

  const body: ResultInput = { test_name: name };
  if (NUMBER.test(value)) body.value_numeric = Number(value);
  else body.value_text = value;
  if (form.unit.trim()) body.unit = form.unit.trim();
  if (form.comment.trim()) body.comment = form.comment.trim();

  const fields: [keyof ResultInput, string, string][] = [
    ['ref_low', form.refLow, 'Normal range (low)'],
    ['ref_high', form.refHigh, 'Normal range (high)'],
    ['critical_low', form.criticalLow, 'Critical (low)'],
    ['critical_high', form.criticalHigh, 'Critical (high)'],
  ];
  for (const [key, raw, label] of fields) {
    const r = optionalNumber(raw, label);
    if (r.error) return { error: r.error };
    if (r.n !== undefined) (body as Record<string, unknown>)[key] = r.n;
  }
  if (!('value_numeric' in body) && fields.some(([k]) => k in body)) {
    return { error: 'Ranges only apply to a numeric result.' };
  }
  if (body.ref_low !== undefined && body.ref_high !== undefined && body.ref_low > body.ref_high) {
    return { error: 'The low end of the normal range is above the high end.' };
  }
  if (body.critical_low !== undefined && body.critical_high !== undefined && body.critical_low > body.critical_high) {
    return { error: 'The low critical value is above the high one.' };
  }
  return { body };
}

const URGENT_FIRST: Record<string, number> = { STAT: 0, URGENT: 1, ROUTINE: 2 };
export const byPriority = <T extends { priority: string }>(rows: T[]): T[] =>
  [...rows].sort((a, b) => (URGENT_FIRST[a.priority] ?? 3) - (URGENT_FIRST[b.priority] ?? 3));

/** Critical first, then abnormal, then normal, oldest first within each, so nothing dangerous waits behind routine work. */
const SEVERITY: Record<string, number> = { CRITICAL_LOW: 0, CRITICAL_HIGH: 0, LOW: 1, HIGH: 1, UNKNOWN: 1, NORMAL: 2 };
export function reviewOrder(rows: ReportedResult[]): ReportedResult[] {
  return [...rows].sort(
    (a, b) =>
      (SEVERITY[a.interpretation] ?? 1) - (SEVERITY[b.interpretation] ?? 1) ||
      a.reported_at.localeCompare(b.reported_at),
  );
}
export const isCritical = (r: ReportedResult) => r.interpretation.startsWith('CRITICAL');

export function describeValue(r: ReportedResult): string {
  const v = r.value_numeric ?? r.value_text ?? '';
  const range = r.ref_low !== null || r.ref_high !== null ? ` (normal ${r.ref_low ?? '…'}–${r.ref_high ?? '…'})` : '';
  return `${v}${r.unit ? ` ${r.unit}` : ''}${range}`;
}

export type FollowUpGroup = { key: 'overdue' | 'today' | 'week' | 'later'; title: string; rows: WorklistFollowUp[] };

/** `today` is a YYYY-MM-DD string in the clinic's local calendar. Dates compare as strings, which is safe for ISO dates. */
export function groupFollowUps(rows: WorklistFollowUp[], today: string, weekEnd: string): FollowUpGroup[] {
  const groups: FollowUpGroup[] = [
    { key: 'overdue', title: 'Overdue', rows: [] },
    { key: 'today', title: 'Due today', rows: [] },
    { key: 'week', title: 'This week', rows: [] },
    { key: 'later', title: 'Later', rows: [] },
  ];
  for (const r of [...rows].sort((a, b) => a.due_date.localeCompare(b.due_date))) {
    const g = r.due_date < today ? 0 : r.due_date === today ? 1 : r.due_date <= weekEnd ? 2 : 3;
    groups[g].rows.push(r);
  }
  return groups.filter((g) => g.rows.length > 0);
}

export const KIND_LABEL: Record<string, string> = {
  REVIEW: 'Review visit',
  INVESTIGATION_RESULT: 'Investigation result',
  MEDICATION_REVIEW: 'Medication review',
  REFERRAL: 'Referral',
  OTHER: 'Other',
};

/** Cover windows are checked here to save a round trip; the server applies the same limits. */
export const MAX_COVER_DAYS = 31;
export function coverProblem(startsOn: string, endsOn: string, today: string): string | null {
  const ok = /^\d{4}-\d{2}-\d{2}$/;
  if (!ok.test(startsOn) || !ok.test(endsOn)) return 'Enter dates as YYYY-MM-DD.';
  if (endsOn < startsOn) return 'The end date is before the start date.';
  if (endsOn < today) return 'That period has already ended.';
  const days = (Date.parse(endsOn) - Date.parse(startsOn)) / 86_400_000;
  if (days >= MAX_COVER_DAYS) return `Cover can last at most ${MAX_COVER_DAYS} days.`;
  return null;
}

export type DispenseState = { label: string; tone: 'neutral' | 'success' | 'warning'; canRecord: boolean };

/** The newest record decides. Fully dispensed is final; anything else can still be followed up. */
export function dispenseState(history: { status: string; created_at: string }[]): DispenseState {
  const latest = [...history].sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  if (!latest) return { label: 'Not dispensed yet', tone: 'neutral', canRecord: true };
  if (latest.status === 'DISPENSED') return { label: 'Fully dispensed', tone: 'success', canRecord: false };
  if (latest.status === 'PARTIALLY_DISPENSED') return { label: 'Partly dispensed', tone: 'warning', canRecord: true };
  return { label: 'Not dispensed', tone: 'warning', canRecord: true };
}

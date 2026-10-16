import type { EncounterDetail } from '@/api/schemas';

import { formatVital, needsVerification } from './clinical';

const NOTE_TITLES: Record<string, string> = {
  CHIEF_COMPLAINT: 'Reason for visit',
  TRIAGE: 'Triage',
  HPI: 'History of present illness',
  PAST_HISTORY: 'Past history',
  FAMILY_HISTORY: 'Family history',
  SOCIAL_HISTORY: 'Social history',
  EXAMINATION: 'Examination',
  ASSESSMENT: 'Assessment',
  PLAN: 'Plan',
};
const NOTE_ORDER = Object.keys(NOTE_TITLES);
const VITAL_NAMES: Record<string, string> = {
  BP_SYSTOLIC: 'BP systolic', BP_DIASTOLIC: 'BP diastolic', HEART_RATE: 'Pulse', RESP_RATE: 'Respiratory rate',
  TEMPERATURE: 'Temperature', SPO2: 'SpO2', WEIGHT: 'Weight', HEIGHT: 'Height',
};

const mark = (verification: string): string => (needsVerification(verification) ? ' [unverified]' : '');

/**
 * Plain text of a visit for pasting into another system. It is only what is already in the record:
 * notes and diagnoses with any unverified entry marked, signed prescriptions (never drafts), placed
 * tests and follow-ups. Nothing is rewritten, summarised or added.
 */
export function visitText(d: EncounterDetail, patientLine: string): string {
  const out: string[] = [patientLine, ''];
  const notes = [...d.notes].sort((a, b) => NOTE_ORDER.indexOf(a.note_type) - NOTE_ORDER.indexOf(b.note_type));
  for (const n of notes) out.push(`${NOTE_TITLES[n.note_type] ?? n.note_type}: ${n.content}${mark(n.verification_state)}`);
  if (d.vitals.length > 0) {
    out.push('', 'Vital signs:');
    for (const v of d.vitals) out.push(`- ${VITAL_NAMES[v.code] ?? v.code}: ${formatVital(v)}${mark(v.verification_state)}`);
  }
  if (d.conditions.length > 0) {
    out.push('', 'Diagnoses:');
    for (const c of d.conditions) out.push(`- ${c.display} (${c.certainty.toLowerCase()})${mark(c.verification_state)}`);
  }
  const signed = d.prescriptions.filter((p) => p.status === 'SIGNED');
  if (signed.length > 0) {
    out.push('', 'Prescription:');
    for (const p of signed) {
      for (const i of p.items) {
        const days = i.duration_days ? ` for ${i.duration_days} days` : '';
        const extra = i.instructions ? ` (${i.instructions})` : '';
        out.push(`- ${i.medicine_name}${i.strength ? ` ${i.strength}` : ''}: ${i.dose}, ${i.route.toLowerCase()}, ${i.frequency}${days}${extra}`);
      }
    }
  }
  const tests = d.orders.filter((o) => o.status !== 'DRAFT' && o.status !== 'CANCELLED');
  if (tests.length > 0) {
    out.push('', 'Tests ordered:');
    for (const o of tests) out.push(`- ${o.name} (${o.category.toLowerCase()}, ${o.priority.toLowerCase()})`);
  }
  const follow = d.follow_ups.filter((f) => f.status !== 'CANCELLED');
  if (follow.length > 0) {
    out.push('', 'Follow-up:');
    for (const f of follow) out.push(`- ${f.due_date}: ${f.reason}`);
  }
  return out.join('\n').trim();
}

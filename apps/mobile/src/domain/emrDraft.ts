import type { Candidate } from '@/api/schemas';

/**
 * The draft medical record built from what was said, laid out the way a clinic note is read. Code only:
 * it places each finding the software heard under its heading and words it plainly. It writes no
 * sentences of its own, adds nothing that was not heard, and never fills a gap. An empty heading says
 * nothing was heard about it, which is not the same as "none".
 */

export type SectionKey =
  | 'complaint' | 'illness' | 'past' | 'medicines' | 'allergies' | 'family'
  | 'examination' | 'assessment' | 'tests' | 'treatment' | 'followup';

export const SECTIONS: { key: SectionKey; title: string; kinds: string[] }[] = [
  { key: 'complaint', title: 'Reason for visit', kinds: ['CHIEF_COMPLAINT'] },
  { key: 'illness', title: 'History of present illness', kinds: ['SYMPTOM', 'CIRCUMSTANCE'] },
  { key: 'past', title: 'Past medical and surgical history', kinds: ['MEDICAL_HISTORY', 'SURGICAL_HISTORY', 'PREVIOUS_TREATMENT'] },
  { key: 'medicines', title: 'Current medicines', kinds: ['MEDICATION'] },
  { key: 'allergies', title: 'Allergies', kinds: ['ALLERGY'] },
  { key: 'family', title: 'Family and social history', kinds: ['FAMILY_HISTORY', 'SOCIAL_HISTORY'] },
  { key: 'examination', title: 'Examination and measurements', kinds: ['EXAMINATION_FINDING', 'VITAL_MENTIONED'] },
  { key: 'assessment', title: 'Assessment (as said by the doctor)', kinds: ['DIAGNOSIS_DISCUSSED'] },
  { key: 'tests', title: 'Plan: tests', kinds: ['INVESTIGATION_DISCUSSED'] },
  { key: 'treatment', title: 'Plan: treatment', kinds: ['TREATMENT_DISCUSSED'] },
  { key: 'followup', title: 'Plan: follow-up', kinds: ['FOLLOW_UP'] },
];

const PREFIX: Record<string, string> = { PRESENT: '', ABSENT: 'Denies: ', POSSIBLE: 'Possible: ', HISTORICAL: 'Past: ' };

/** One line of the note, e.g. "Lower back pain (site: left leg; duration: 3 weeks)". */
export function lineText(c: Candidate): string {
  const text = c.edited_text ?? c.text;
  const prefix = c.subject === 'FAMILY_MEMBER' ? 'Family history: ' : (PREFIX[c.assertion] ?? '');
  const detail = Object.entries(c.attributes).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`).join('; ');
  return `${prefix}${text}${detail ? ` (${detail})` : ''}`;
}

export type DraftLine = { candidate: Candidate; text: string; state: 'review' | 'added' | 'rejected' };
export type DraftSection = { key: SectionKey; title: string; lines: DraftLine[] };
export type Draft = {
  sections: DraftSection[];
  total: number;
  reviewed: number;
  pending: number;
};

const stateOf = (c: Candidate): DraftLine['state'] =>
  c.status === 'PENDING' ? 'review' : c.status === 'REJECTED' ? 'rejected' : 'added';

export function buildDraft(candidates: Candidate[]): Draft {
  const sections = SECTIONS.map((s) => ({
    key: s.key,
    title: s.title,
    lines: candidates
      .filter((c) => s.kinds.includes(c.kind))
      .map((c) => ({ candidate: c, text: lineText(c), state: stateOf(c) })),
  }));
  const placed = sections.flatMap((s) => s.lines);
  const pending = placed.filter((l) => l.state === 'review').length;
  return { sections, total: placed.length, reviewed: placed.length - pending, pending };
}

/** Kinds where accepting a whole group at once is reasonable. Allergies, medicines, diagnoses and plan items are always looked at one by one. */
const BULK_KINDS = new Set([
  'CHIEF_COMPLAINT', 'SYMPTOM', 'CIRCUMSTANCE', 'MEDICAL_HISTORY', 'SURGICAL_HISTORY', 'PREVIOUS_TREATMENT',
  'FAMILY_HISTORY', 'SOCIAL_HISTORY', 'EXAMINATION_FINDING',
]);

/** Pending findings that carry no warning, are not hedged and are stated plainly: safe to accept together. */
export const clearToAccept = (lines: DraftLine[]): Candidate[] =>
  lines
    .filter((l) => l.state === 'review')
    .map((l) => l.candidate)
    .filter((c) => BULK_KINDS.has(c.kind) && c.risk_flags.length === 0 && c.assertion !== 'POSSIBLE');

/** The one-line status shown at the top of the draft. */
export function progressText(d: Draft): string {
  if (d.total === 0) return 'Nothing clinical was picked out of the conversation yet.';
  if (d.pending === 0) return `All ${d.total} items reviewed.`;
  return `${d.reviewed} of ${d.total} reviewed. ${d.pending} still waiting for you.`;
}

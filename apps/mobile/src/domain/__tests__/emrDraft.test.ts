import type { Candidate } from '@/api/schemas';

import { buildDraft, clearToAccept, lineText, progressText } from '../emrDraft';

const cand = (o: Partial<Candidate>): Candidate => ({
  id: 'x', interaction_id: 'i', encounter_id: 'e', kind: 'SYMPTOM', text: 'fever', assertion: 'PRESENT', subject: 'PATIENT',
  attributes: {}, original_term: null, evidence: [], risk_flags: [], status: 'PENDING', edited_text: null, result_kind: null,
  created_at: 'now', follow_up_in_days: null, ...o,
});

describe('lineText', () => {
  it('words a finding plainly and keeps denials, doubt and family members visible', () => {
    expect(lineText(cand({ text: 'lower back pain', attributes: { site: 'left leg', duration: '3 weeks' } }))).toBe('lower back pain (site: left leg; duration: 3 weeks)');
    expect(lineText(cand({ assertion: 'ABSENT', text: 'fever' }))).toBe('Denies: fever');
    expect(lineText(cand({ assertion: 'POSSIBLE', text: 'numbness' }))).toBe('Possible: numbness');
    expect(lineText(cand({ kind: 'FAMILY_HISTORY', subject: 'FAMILY_MEMBER', text: 'slipped disc (father)' }))).toBe('Family history: slipped disc (father)');
    expect(lineText(cand({ text: 'fever', edited_text: 'fever for 2 days' }))).toBe('fever for 2 days');
  });
});

describe('buildDraft', () => {
  const draft = buildDraft([
    cand({ id: '1', kind: 'CHIEF_COMPLAINT', text: 'back pain', status: 'ACCEPTED' }),
    cand({ id: '2', kind: 'SYMPTOM', text: 'leg numbness' }),
    cand({ id: '3', kind: 'CIRCUMSTANCE', text: 'fell from scooter' }),
    cand({ id: '4', kind: 'ALLERGY', text: 'penicillin' }),
    cand({ id: '5', kind: 'SYMPTOM', text: 'cough', status: 'REJECTED' }),
    cand({ id: '6', kind: 'FOLLOW_UP', text: 'return in 5 days' }),
  ]);
  it('files each finding under its heading in a fixed order and leaves unheard headings empty', () => {
    expect(draft.sections.map((s) => s.title).slice(0, 3)).toEqual(['Reason for visit', 'History of present illness', 'Past medical and surgical history']);
    const illness = draft.sections.find((s) => s.key === 'illness');
    expect(illness?.lines.map((l) => l.candidate.id)).toEqual(['2', '3', '5']);
    expect(draft.sections.find((s) => s.key === 'examination')?.lines).toEqual([]);
  });
  it('counts what is still waiting and what has been decided', () => {
    expect(draft).toMatchObject({ total: 6, reviewed: 2, pending: 4 });
    expect(draft.sections.find((s) => s.key === 'illness')?.lines.map((l) => l.state)).toEqual(['review', 'review', 'rejected']);
    expect(progressText(draft)).toBe('2 of 6 reviewed. 4 still waiting for you.');
    expect(progressText(buildDraft([]))).toMatch(/Nothing clinical/);
    expect(progressText(buildDraft([cand({ status: 'ACCEPTED' })]))).toBe('All 1 items reviewed.');
  });
});

describe('clearToAccept', () => {
  it('only offers plainly stated history and symptoms, never allergies, medicines, diagnoses, plans or anything flagged', () => {
    const lines = buildDraft([
      cand({ id: 'a', kind: 'SYMPTOM' }),
      cand({ id: 'b', kind: 'SYMPTOM', risk_flags: ['negation_cue_check'] }),
      cand({ id: 'c', kind: 'SYMPTOM', assertion: 'POSSIBLE' }),
      cand({ id: 'd', kind: 'ALLERGY' }),
      cand({ id: 'e', kind: 'DIAGNOSIS_DISCUSSED' }),
      cand({ id: 'f', kind: 'MEDICATION' }),
      cand({ id: 'g', kind: 'TREATMENT_DISCUSSED' }),
      cand({ id: 'h', kind: 'CIRCUMSTANCE' }),
      cand({ id: 'i', kind: 'SYMPTOM', status: 'ACCEPTED' }),
    ]).sections.flatMap((s) => s.lines);
    expect(clearToAccept(lines).map((c) => c.id).sort()).toEqual(['a', 'h']);
  });
});

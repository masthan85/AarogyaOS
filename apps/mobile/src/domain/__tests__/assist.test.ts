import type { Candidate, Suggestion } from '@/api/schemas';

import { acceptOutcome, canReviewKind, flagLabel, isSafetyCategory, orderSuggestions, pendingCandidates } from '../assist';

const cand = (o: Partial<Candidate>): Candidate => ({
  id: '1', interaction_id: 'i', encounter_id: 'e', kind: 'SYMPTOM', text: 'fever', assertion: 'PRESENT', subject: 'PATIENT',
  attributes: {}, original_term: null, evidence: [], risk_flags: [], status: 'PENDING', edited_text: null, result_kind: null,
  created_at: '2026-01-01T00:00:00Z', ...o,
});
const sug = (o: Partial<Suggestion>): Suggestion => ({
  id: '1', encounter_id: 'e', category: 'GUIDELINE', title: 't', explanation: 'x', uncertainty: 'MEDIUM', uncertainty_note: null,
  supporting_context: [], evidence_sources: [], payload: {}, warnings: [], origin: 'MODEL', provider: null, model: null,
  status: 'PENDING', created_at: '2026-01-01T00:00:00Z', ...o,
});

describe('assist helpers', () => {
  it('shows safety warnings first, then rule-based items, then model proposals', () => {
    const out = orderSuggestions([
      sug({ id: 'm', origin: 'MODEL' }),
      sug({ id: 'r', origin: 'DETERMINISTIC', category: 'IMPORTANT_INFORMATION' }),
      sug({ id: 'a', origin: 'DETERMINISTIC', category: 'ALLERGY_WARNING' }),
    ]);
    expect(out.map((s) => s.id)).toEqual(['a', 'r', 'm']);
    expect(isSafetyCategory('ALLERGY_WARNING')).toBe(true);
    expect(isSafetyCategory('GUIDELINE')).toBe(false);
  });

  it('mirrors the server rule on who may review which kind', () => {
    expect(canReviewKind('SYMPTOM', false)).toBe(true);
    expect(canReviewKind('DIAGNOSIS_DISCUSSED', false)).toBe(false);
    expect(canReviewKind('DIAGNOSIS_DISCUSSED', true)).toBe(true);
  });

  it('never describes acceptance as more than it does', () => {
    expect(acceptOutcome(cand({ kind: 'DIAGNOSIS_DISCUSSED' }))).toMatch(/suspected/);
    expect(acceptOutcome(cand({ kind: 'INVESTIGATION_DISCUSSED' }))).toMatch(/draft/);
    expect(acceptOutcome(cand({ kind: 'TREATMENT_DISCUSSED' }))).toMatch(/Nothing is prescribed/);
    expect(acceptOutcome(cand({ kind: 'ALLERGY', assertion: 'ABSENT' }))).toMatch(/denies/);
  });

  it('keeps only items still waiting for review', () => {
    expect(pendingCandidates([cand({ status: 'PENDING' }), cand({ status: 'REJECTED' })])).toHaveLength(1);
  });

  it('turns unknown flags into readable text', () => {
    expect(flagLabel('negation_cue_check')).toMatch(/denial/);
    expect(flagLabel('some_new_flag')).toBe('some new flag');
  });
});

import type { Candidate, Suggestion } from '@/api/schemas';

/** How a candidate's meaning is shown: a negation must never look like a positive finding. */
export const ASSERTION_LABELS: Record<string, string> = {
  PRESENT: 'Present',
  ABSENT: 'Patient denies',
  POSSIBLE: 'Possible',
  HISTORICAL: 'In the past',
};

export const KIND_LABELS: Record<string, string> = {
  CHIEF_COMPLAINT: 'Reason for visit',
  SYMPTOM: 'Symptom',
  MEDICAL_HISTORY: 'Medical history',
  SURGICAL_HISTORY: 'Surgical history',
  FAMILY_HISTORY: 'Family history',
  SOCIAL_HISTORY: 'Social history',
  MEDICATION: 'Medicine',
  ALLERGY: 'Allergy',
  PREVIOUS_TREATMENT: 'Previous treatment',
  EXAMINATION_FINDING: 'Examination',
  VITAL_MENTIONED: 'Vital sign mentioned',
  DIAGNOSIS_DISCUSSED: 'Diagnosis discussed',
  INVESTIGATION_DISCUSSED: 'Test discussed',
  TREATMENT_DISCUSSED: 'Treatment discussed',
  FOLLOW_UP: 'Follow-up',
};

export const CATEGORY_LABELS: Record<string, string> = {
  IMPORTANT_INFORMATION: 'Worth knowing',
  MISSING_HISTORY_QUESTION: 'Question to consider asking',
  DIFFERENTIAL: 'Possibility to consider',
  INVESTIGATION: 'Test to consider',
  MEDICATION_CONSIDERATION: 'Medicine to consider',
  INTERACTION: 'Interaction',
  CONTRAINDICATION: 'Contraindication',
  ALLERGY_WARNING: 'Allergy warning',
  PREVIOUS_INFORMATION: 'From earlier records',
  ABNORMAL_RESULT: 'Abnormal result',
  GUIDELINE: 'Reference',
  REFERRAL: 'Referral to consider',
  FOLLOW_UP: 'Follow-up to consider',
  PATIENT_EDUCATION: 'Advice to consider',
};

const SAFETY = new Set(['ALLERGY_WARNING', 'INTERACTION', 'CONTRAINDICATION']);
export const isSafetyCategory = (c: string): boolean => SAFETY.has(c);

/** Kinds a nurse may review; everything else needs the encounter's doctor. Mirrors the server. */
const NURSE_KINDS = new Set(['CHIEF_COMPLAINT', 'SYMPTOM', 'VITAL_MENTIONED', 'ALLERGY', 'MEDICATION']);
export const canReviewKind = (kind: string, isDoctor: boolean): boolean => isDoctor || NURSE_KINDS.has(kind);

/** Flags worth putting in front of the clinician before they accept. */
const FLAG_LABELS: Record<string, string> = {
  hedged_downgraded: 'Said with doubt, so shown as "possible"',
  negation_cue_check: 'May be a denial: check the quote',
  speaker_unassigned: 'Speaker not identified: check who said it',
  stated_by_clinician: 'Said by the clinician, not the patient',
  unknown_attributes_removed: 'Some detail was removed because it was not allowed',
};
export const flagLabel = (f: string): string => FLAG_LABELS[f] ?? f.replace(/_/g, ' ');

export const pendingCandidates = (c: Candidate[]): Candidate[] => c.filter((x) => x.status === 'PENDING');
export const pendingSuggestions = (s: Suggestion[]): Suggestion[] => s.filter((x) => x.status === 'PENDING');

/** Safety warnings first, then anything the rules produced, then model proposals. */
export function orderSuggestions(list: Suggestion[]): Suggestion[] {
  const rank = (s: Suggestion) => (isSafetyCategory(s.category) ? 0 : s.origin === 'DETERMINISTIC' ? 1 : 2);
  return [...list].sort((a, b) => rank(a) - rank(b) || a.created_at.localeCompare(b.created_at));
}

export const uncertaintyLabel = (u: string): string =>
  u === 'LOW' ? 'Low uncertainty' : u === 'HIGH' ? 'High uncertainty' : 'Some uncertainty';

/** A short line the clinician can scan: what the software suggests this becomes if accepted. */
export function acceptOutcome(c: Candidate): string {
  switch (c.kind) {
    case 'DIAGNOSIS_DISCUSSED':
      return 'Recorded as a suspected diagnosis, not a confirmed one';
    case 'INVESTIGATION_DISCUSSED':
      return 'Saved as a draft test you still have to order';
    case 'TREATMENT_DISCUSSED':
      return 'Saved as a plan note. Nothing is prescribed';
    case 'ALLERGY':
      return c.assertion === 'ABSENT' ? 'Saved as a note: patient denies this allergy' : 'Recorded as an allergy';
    case 'MEDICATION':
      return c.assertion === 'ABSENT' ? 'Saved as a note: not taking this' : 'Recorded as a medicine the patient takes';
    default:
      return 'Saved as a note in this visit';
  }
}

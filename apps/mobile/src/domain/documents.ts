import type { ClinicalDocument, NoteTemplate } from '@/api/schemas';

/** What to save from a filled-in template: one note per section that has words in it. */
export type NoteToSave = { note_type: string; content: string; source: 'DOCTOR_ENTERED' | 'PATIENT_REPORTED' };

const PATIENT_TOLD = new Set(['HPI', 'PAST_HISTORY', 'FAMILY_HISTORY', 'SOCIAL_HISTORY']);

export function notesFromTemplate(template: NoteTemplate, values: Record<string, string>): NoteToSave[] {
  return template.sections
    .map((s) => ({ s, text: (values[s.title] ?? '').trim() }))
    .filter((x) => x.text.length > 0)
    .map(({ s, text }) => ({
      note_type: s.note_type,
      // Use the section's title as a lead-in only when several sections share one note type,
      // so two "Plan" style sections stay distinguishable in the record.
      content: template.sections.filter((o) => o.note_type === s.note_type).length > 1 ? `${s.title}: ${text}` : text,
      source: PATIENT_TOLD.has(s.note_type) ? 'PATIENT_REPORTED' : 'DOCTOR_ENTERED',
    }));
}

export const filledSections = (template: NoteTemplate, values: Record<string, string>): number =>
  template.sections.filter((s) => (values[s.title] ?? '').trim().length > 0).length;

export const DOCUMENT_LABELS: Record<string, string> = {
  VISIT_SUMMARY: 'Visit summary for the patient',
  REFERRAL_LETTER: 'Referral letter',
};

/** Latest version of each document (per kind and recipient), newest first. Superseded ones are hidden. */
export function currentDocuments(docs: ClinicalDocument[]): ClinicalDocument[] {
  return docs.filter((d) => d.status !== 'SUPERSEDED').sort((a, b) => b.created_at.localeCompare(a.created_at));
}

export const documentTitle = (d: ClinicalDocument): string =>
  d.kind === 'REFERRAL_LETTER' && d.recipient ? `Referral to ${d.recipient}` : (DOCUMENT_LABELS[d.kind] ?? d.kind);

export const translationNote = (d: ClinicalDocument): string | null => {
  switch (d.translation_status) {
    case 'NOT_AVAILABLE':
      return 'No translation service is connected, so this is in English.';
    case 'NOT_CONSENTED':
      return 'Not translated: it needs the organisation\'s AI switch and the patient\'s AI-processing consent. This is in English.';
    case 'MACHINE_DRAFT':
      return 'Machine-translated draft: read it, and check every medicine and number, before approving.';
    case 'NUMBERS_MISMATCH':
      return 'Warning: the numbers in the translation differ from the English. Compare every dose and date before approving.';
    default:
      return null;
  }
};

/** Reading aloud is offered only for approved text, in languages the voice service covers. */
export const SPEECH_LANGUAGES = new Set(['en-IN', 'hi-IN', 'bn-IN', 'gu-IN', 'kn-IN', 'ml-IN', 'mr-IN', 'od-IN', 'pa-IN', 'ta-IN', 'te-IN']);
export const canReadAloud = (d: ClinicalDocument): boolean => d.status === 'APPROVED' && SPEECH_LANGUAGES.has(d.language);

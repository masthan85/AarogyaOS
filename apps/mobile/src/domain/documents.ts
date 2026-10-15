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

export const translationNote = (d: ClinicalDocument): string | null =>
  d.translation_status === 'NOT_AVAILABLE'
    ? 'No translation service is connected, so this is in English.'
    : d.translation_status === 'MACHINE_DRAFT'
      ? 'Machine-translated draft: check it before approving.'
      : null;

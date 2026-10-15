import type { ClinicalDocument, NoteTemplate } from '@/api/schemas';

import { canReadAloud, currentDocuments, documentTitle, filledSections, notesFromTemplate, translationNote } from '../documents';

const template: NoteTemplate = {
  id: 't', name: 'Review', specialty: null, active: true, builtin: false,
  sections: [
    { note_type: 'HPI', title: 'Symptoms', hint: '' },
    { note_type: 'EXAMINATION', title: 'Feet', hint: '' },
    { note_type: 'EXAMINATION', title: 'Eyes', hint: '' },
    { note_type: 'PLAN', title: 'Plan', hint: '' },
  ],
};
const doc = (o: Partial<ClinicalDocument>): ClinicalDocument => ({
  id: '1', encounter_id: 'e', kind: 'VISIT_SUMMARY', recipient: null, version: 1, language: 'en-IN', content: 'x',
  source_content: 'x', translation_status: 'NOT_NEEDED', status: 'DRAFT', approved_at: null, created_at: '2026-01-01', ...o,
});

describe('notesFromTemplate', () => {
  it('saves only sections that have words, and never invents text', () => {
    const notes = notesFromTemplate(template, { Symptoms: '  thirst  ', Plan: '   ' });
    expect(notes).toEqual([{ note_type: 'HPI', content: 'thirst', source: 'PATIENT_REPORTED' }]);
    expect(notesFromTemplate(template, {})).toEqual([]);
  });

  it('marks what the patient told you apart from what you found', () => {
    const notes = notesFromTemplate(template, { Symptoms: 'a', Plan: 'b' });
    expect(notes.map((n) => n.source)).toEqual(['PATIENT_REPORTED', 'DOCTOR_ENTERED']);
  });

  it('keeps two sections of the same type distinguishable', () => {
    const notes = notesFromTemplate(template, { Feet: 'no ulcer', Eyes: 'clear' });
    expect(notes.map((n) => n.content)).toEqual(['Feet: no ulcer', 'Eyes: clear']);
    expect(filledSections(template, { Feet: 'x', Eyes: ' ' })).toBe(1);
  });
});

describe('documents', () => {
  it('hides superseded versions and titles letters by recipient', () => {
    const docs = [doc({ id: 'a', status: 'SUPERSEDED' }), doc({ id: 'b', kind: 'REFERRAL_LETTER', recipient: 'Dr Rao' })];
    expect(currentDocuments(docs).map((d) => d.id)).toEqual(['b']);
    expect(documentTitle(docs[1])).toBe('Referral to Dr Rao');
  });

  it('warns loudly when translated numbers differ and when consent is missing', () => {
    expect(translationNote(doc({ translation_status: 'NUMBERS_MISMATCH' }))).toMatch(/numbers/);
    expect(translationNote(doc({ translation_status: 'NOT_CONSENTED' }))).toMatch(/consent/);
  });

  it('offers reading aloud only for approved text in a supported language', () => {
    expect(canReadAloud(doc({ status: 'DRAFT' }))).toBe(false);
    expect(canReadAloud(doc({ status: 'APPROVED', language: 'hi-IN' }))).toBe(true);
    expect(canReadAloud(doc({ status: 'APPROVED', language: 'ur-IN' }))).toBe(false);
  });

  it('says plainly when a translation is missing or unchecked', () => {
    expect(translationNote(doc({ translation_status: 'NOT_AVAILABLE' }))).toMatch(/English/);
    expect(translationNote(doc({ translation_status: 'MACHINE_DRAFT' }))).toMatch(/check/);
    expect(translationNote(doc({}))).toBeNull();
  });
});

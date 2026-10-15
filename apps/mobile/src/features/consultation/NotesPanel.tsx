import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Text, View } from 'react-native';

import { addNote, getNoteTemplates } from '@/api/endpoints';
import type { NoteTemplate } from '@/api/schemas';
import { Button, Card, ChoiceChips, SectionTitle, TextField } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
import { filledSections, notesFromTemplate } from '@/domain/documents';

import { FactRow } from './FactRow';
import { useAction } from './useAction';
import type { EncounterData } from './useEncounterData';

const TYPES = [
  { value: 'HPI', label: 'History of illness' },
  { value: 'PAST_HISTORY', label: 'Past history' },
  { value: 'FAMILY_HISTORY', label: 'Family' },
  { value: 'SOCIAL_HISTORY', label: 'Social' },
  { value: 'EXAMINATION', label: 'Examination' },
  { value: 'ASSESSMENT', label: 'Assessment' },
  { value: 'PLAN', label: 'Plan' },
] as const;
type NoteType = (typeof TYPES)[number]['value'];
const TITLES: Record<string, string> = { CHIEF_COMPLAINT: 'Complaint', TRIAGE: 'Triage', GENERAL: 'Note', ...Object.fromEntries(TYPES.map((x) => [x.value, x.label])) };

export function NotesPanel({ encId, data }: { encId: string; data: EncounterData }) {
  const t = useTheme();
  const [type, setType] = useState<NoteType>('HPI');
  const [fromPatient, setFromPatient] = useState(true);
  const [text, setText] = useState('');
  const save = useAction(
    () => addNote(encId, { note_type: type, content: text, source: fromPatient && ['HPI', 'PAST_HISTORY', 'FAMILY_HISTORY', 'SOCIAL_HISTORY'].includes(type) ? 'PATIENT_REPORTED' : 'DOCTOR_ENTERED' }),
    () => { setText(''); void data.refresh(); },
  );
  const notes = data.detail?.notes ?? [];
  const templates = useQuery({ queryKey: ['note-templates'], queryFn: getNoteTemplates, gcTime: 0 });
  const [template, setTemplate] = useState<NoteTemplate | null>(null);
  return (
    <View style={{ gap: space.md }}>
      <SectionTitle>Notes for this visit</SectionTitle>
      <Card>
        {notes.length === 0 ? <Text style={{ color: t.textMuted }}>Nothing written yet.</Text> : null}
        {notes.map((n) => (
          <FactRow key={n.id} title={`${TITLES[n.note_type] ?? n.note_type}: ${n.content}`} source={n.source} verification={n.verification_state} />
        ))}
      </Card>
      {templates.data && templates.data.length > 0 ? (
        <Card title="Use a layout">
          <ChoiceChips
            value={(template?.id ?? 'none') as string}
            onChange={(id) => setTemplate(templates.data?.find((x) => x.id === id) ?? null)}
            options={[{ value: 'none', label: 'Free note' }, ...templates.data.map((x) => ({ value: x.id, label: x.name }))]}
          />
          {template ? <TemplateForm key={template.id} encId={encId} template={template} onSaved={() => { setTemplate(null); void data.refresh(); }} onPartial={() => void data.refresh()} /> : null}
        </Card>
      ) : null}
      {template ? null : (
      <Card title="Add a note">
        <ChoiceChips value={type} onChange={setType} options={[...TYPES]} />
        {['HPI', 'PAST_HISTORY', 'FAMILY_HISTORY', 'SOCIAL_HISTORY'].includes(type) ? (
          <ChoiceChips value={fromPatient ? 'patient' : 'me'} onChange={(v) => setFromPatient(v === 'patient')}
            options={[{ value: 'patient', label: 'Patient told me' }, { value: 'me', label: 'My finding' }]} />
        ) : null}
        <TextField label="Note" value={text} onChangeText={setText} multiline />
        <Button title="Save note" disabled={!text.trim()} loading={save.pending} onPress={() => void save.run()} />
      </Card>
      )}
    </View>
  );
}

/** A layout only gives headings; every word saved is the doctor's. One note per filled section. */
function TemplateForm({ encId, template, onSaved, onPartial }: { encId: string; template: NoteTemplate; onSaved: () => void; onPartial: () => void }) {
  const t = useTheme();
  const [values, setValues] = useState<Record<string, string>>({});
  const save = useAction(
    async () => {
      try {
        for (const n of notesFromTemplate(template, values)) await addNote(encId, n);
      } finally {
        onPartial(); // if one section failed, the earlier ones are saved: show them
      }
    },
    onSaved,
  );
  return (
    <View style={{ gap: space.sm }}>
      {template.sections.map((sec) => (
        <TextField key={sec.title} label={sec.title} placeholder={sec.hint || undefined} multiline
          value={values[sec.title] ?? ''} onChangeText={(v) => setValues((prev) => ({ ...prev, [sec.title]: v }))} />
      ))}
      <Text style={{ color: t.textMuted, fontSize: 12 }}>Empty sections are skipped. Each filled section is saved as its own note.</Text>
      <Button title={`Save ${filledSections(template, values)} section(s)`} disabled={filledSections(template, values) === 0}
        loading={save.pending} onPress={() => void save.run()} />
    </View>
  );
}

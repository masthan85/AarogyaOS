import { useState } from 'react';
import { Text, View } from 'react-native';

import { addNote } from '@/api/endpoints';
import { Button, Card, ChoiceChips, SectionTitle, TextField } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';

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
  return (
    <View style={{ gap: space.md }}>
      <SectionTitle>Notes for this visit</SectionTitle>
      <Card>
        {notes.length === 0 ? <Text style={{ color: t.textMuted }}>Nothing written yet.</Text> : null}
        {notes.map((n) => (
          <FactRow key={n.id} title={`${TITLES[n.note_type] ?? n.note_type}: ${n.content}`} source={n.source} verification={n.verification_state} />
        ))}
      </Card>
      <Card title="Add a note">
        <ChoiceChips value={type} onChange={setType} options={[...TYPES]} />
        {['HPI', 'PAST_HISTORY', 'FAMILY_HISTORY', 'SOCIAL_HISTORY'].includes(type) ? (
          <ChoiceChips value={fromPatient ? 'patient' : 'me'} onChange={(v) => setFromPatient(v === 'patient')}
            options={[{ value: 'patient', label: 'Patient told me' }, { value: 'me', label: 'My finding' }]} />
        ) : null}
        <TextField label="Note" value={text} onChangeText={setText} multiline />
        <Button title="Save note" disabled={!text.trim()} loading={save.pending} onPress={() => void save.run()} />
      </Card>
    </View>
  );
}

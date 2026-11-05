import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { ScrollView, Text, View } from 'react-native';

import { createTemplate, getAllTemplates, updateTemplate } from '@/api/endpoints';
import type { NoteTemplate } from '@/api/schemas';
import { Button, Card, ChoiceChips, EmptyState, LoadingState, SectionTitle, StatusChip, TextField } from '@/design-system/components';
import { space, useTheme, type } from '@/design-system/tokens';
import { useAction } from '@/features/consultation/useAction';

const TYPES = [
  { value: 'HPI', label: 'History' },
  { value: 'PAST_HISTORY', label: 'Past history' },
  { value: 'FAMILY_HISTORY', label: 'Family' },
  { value: 'SOCIAL_HISTORY', label: 'Social' },
  { value: 'EXAMINATION', label: 'Examination' },
  { value: 'ASSESSMENT', label: 'Assessment' },
  { value: 'PLAN', label: 'Plan' },
];

type Section = { note_type: string; title: string; hint: string };

export function TemplatesScreen() {
  const t = useTheme();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['templates-all'], queryFn: getAllTemplates, gcTime: 0 });
  const refresh = () => void qc.invalidateQueries({ queryKey: ['templates-all'] });
  const [name, setName] = useState('');
  const [specialty, setSpecialty] = useState('');
  const [sections, setSections] = useState<Section[]>([{ note_type: 'HPI', title: '', hint: '' }]);
  const titles = sections.map((s) => s.title.trim().toLowerCase());
  const valid = name.trim().length >= 2 && sections.every((s) => s.title.trim()) && new Set(titles).size === titles.length;
  const add = useAction(
    () => createTemplate({ name: name.trim(), specialty: specialty.trim() || null, active: true, sections: sections.map((s) => ({ ...s, title: s.title.trim(), hint: s.hint.trim() })) }),
    () => { setName(''); setSpecialty(''); setSections([{ note_type: 'HPI', title: '', hint: '' }]); refresh(); },
  );
  if (q.isPending) return <LoadingState label="Loading layouts…" />;
  const own = (q.data ?? []).filter((x) => !x.builtin);

  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md }} keyboardShouldPersistTaps="handled">
      <SectionTitle>Your layouts</SectionTitle>
      {own.length === 0 ? <EmptyState message="None yet. Doctors can use the built-in layouts." /> : null}
      {own.map((x) => <TemplateCard key={x.id} template={x} onChanged={refresh} />)}

      <Card title="New layout">
        <Text style={[type.caption, { color: t.textMuted }]}>A layout is only headings. Nothing is pre-filled: every word saved is the doctor's.</Text>
        <TextField label="Name" value={name} onChangeText={setName} />
        <TextField label="Specialty (optional)" value={specialty} onChangeText={setSpecialty} />
        {sections.map((s, i) => (
          <View key={i} style={{ gap: space.sm, paddingTop: space.sm }}>
            <ChoiceChips label={`Section ${i + 1} is saved as`} value={s.note_type} options={TYPES}
              onChange={(v) => setSections(sections.map((x, j) => (j === i ? { ...x, note_type: v } : x)))} />
            <TextField label="Heading" value={s.title} onChangeText={(v) => setSections(sections.map((x, j) => (j === i ? { ...x, title: v } : x)))} />
            <TextField label="Hint (optional)" value={s.hint} onChangeText={(v) => setSections(sections.map((x, j) => (j === i ? { ...x, hint: v } : x)))} />
            {sections.length > 1 ? <Button title="Remove section" variant="secondary" onPress={() => setSections(sections.filter((_, j) => j !== i))} /> : null}
          </View>
        ))}
        {sections.length < 12 ? <Button title="Add a section" variant="secondary" onPress={() => setSections([...sections, { note_type: 'HPI', title: '', hint: '' }])} /> : null}
        {new Set(titles).size !== titles.length ? <Text style={{ color: t.danger }}>Headings must be different from each other.</Text> : null}
        <Button title="Save layout" disabled={!valid} loading={add.pending} onPress={() => void add.run()} />
      </Card>
    </ScrollView>
  );
}

function TemplateCard({ template, onChanged }: { template: NoteTemplate; onChanged: () => void }) {
  const t = useTheme();
  const toggle = useAction(
    () => updateTemplate(template.id, { name: template.name, specialty: template.specialty, sections: template.sections, active: !template.active }),
    onChanged,
  );
  return (
    <Card title={template.name}>
      <View style={{ flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' }}>
        <StatusChip label={template.active ? 'In use' : 'Hidden'} tone={template.active ? 'success' : 'warning'} />
        {template.specialty ? <StatusChip label={template.specialty} /> : null}
      </View>
      <Text style={{ color: t.textMuted }}>{template.sections.map((s) => s.title).join(' → ')}</Text>
      <Button title={template.active ? 'Hide from doctors' : 'Show to doctors'} variant="secondary" loading={toggle.pending} onPress={() => void toggle.run()} />
    </Card>
  );
}

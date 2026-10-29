import { useState } from 'react';
import { Alert, Text, View } from 'react-native';

import { addCondition, confirmCondition } from '@/api/endpoints';
import { Button, Card, ChoiceChips, SectionTitle, TextField } from '@/design-system/components';
import { space, useTheme, type } from '@/design-system/tokens';

import { FactRow } from './FactRow';
import { useAction } from './useAction';
import type { EncounterData } from './useEncounterData';

type Certainty = 'SUSPECTED' | 'PROVISIONAL' | 'CONFIRMED';

export function DiagnosisPanel({ encId, data }: { encId: string; data: EncounterData }) {
  const t = useTheme();
  const [display, setDisplay] = useState('');
  const [certainty, setCertainty] = useState<Certainty>('PROVISIONAL');
  const [category, setCategory] = useState<'DIAGNOSIS' | 'PROBLEM'>('DIAGNOSIS');
  const add = useAction(() => addCondition(encId, { display, certainty, category }), () => { setDisplay(''); void data.refresh(); });
  const confirm = useAction(confirmCondition, () => void data.refresh());
  const conditions = data.detail?.conditions ?? [];

  return (
    <View style={{ gap: space.md }}>
      <SectionTitle>Diagnoses and problems</SectionTitle>
      <Card>
        {conditions.length === 0 ? <Text style={{ color: t.textMuted }}>None recorded in this visit.</Text> : null}
        {conditions.map((c) => (
          <View key={c.id}>
            <FactRow title={c.display} detail={`${c.category.toLowerCase()} · ${c.certainty.toLowerCase()}`} source={c.source} verification={c.verification_state} />
            {c.certainty !== 'CONFIRMED' ? (
              <Button title="Confirm diagnosis" variant="secondary" loading={confirm.pending}
                onPress={() => Alert.alert('Confirm diagnosis?', c.display, [
                  { text: 'Not yet', style: 'cancel' },
                  { text: 'Confirm', onPress: () => void confirm.run(c.id) },
                ])} />
            ) : null}
          </View>
        ))}
      </Card>
      <Card title="Add">
        <TextField label="Diagnosis or problem" value={display} onChangeText={setDisplay} />
        <ChoiceChips value={category} onChange={setCategory} options={[{ value: 'DIAGNOSIS', label: 'Diagnosis' }, { value: 'PROBLEM', label: 'Long-term problem' }]} />
        <ChoiceChips label="How sure are you?" value={certainty} onChange={setCertainty}
          options={[{ value: 'SUSPECTED', label: 'Suspected' }, { value: 'PROVISIONAL', label: 'Provisional' }, { value: 'CONFIRMED', label: 'Confirmed' }]} />
        <Button title="Add" disabled={display.trim().length < 2} loading={add.pending} onPress={() => void add.run()} />
        <Text style={[type.caption, { color: t.textMuted }]}>
          ICD / SNOMED coding will appear here once a terminology service is connected. Nothing here is coded automatically.
        </Text>
      </Card>
    </View>
  );
}

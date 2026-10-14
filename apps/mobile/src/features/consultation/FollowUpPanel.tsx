import { useState } from 'react';
import { Text, View } from 'react-native';

import { createFollowUp } from '@/api/endpoints';
import { Button, Card, ChoiceChips, SectionTitle, StatusChip, TextField } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
import { addDays, toDateString } from '@/domain/dates';

import { useAction } from './useAction';
import type { EncounterData } from './useEncounterData';

const QUICK = [{ value: '7', label: '1 week' }, { value: '14', label: '2 weeks' }, { value: '30', label: '1 month' }, { value: 'custom', label: 'Pick date' }];

export function FollowUpPanel({ encId, data }: { encId: string; data: EncounterData }) {
  const t = useTheme();
  const [when, setWhen] = useState('7');
  const [custom, setCustom] = useState('');
  const [reason, setReason] = useState('');
  const due = when === 'custom' ? custom : toDateString(addDays(new Date(), Number(when)));
  const save = useAction(() => createFollowUp(encId, { due_date: due, reason }), () => { setReason(''); void data.refresh(); });
  const list = data.detail?.follow_ups ?? [];
  return (
    <View style={{ gap: space.md }}>
      <SectionTitle>Follow-up</SectionTitle>
      <Card>
        {list.length === 0 ? <Text style={{ color: t.textMuted }}>No follow-up planned.</Text> : null}
        {list.map((f) => (
          <View key={f.id} style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <Text style={{ color: t.text }}>{f.due_date} · {f.reason}</Text>
            <StatusChip label={f.status.toLowerCase()} />
          </View>
        ))}
      </Card>
      <Card title="Plan a follow-up">
        <ChoiceChips value={when} onChange={setWhen} options={QUICK} />
        {when === 'custom' ? <TextField label="Date" placeholder="YYYY-MM-DD" value={custom} onChangeText={setCustom} /> : <Text style={{ color: t.textMuted }}>Due {due}</Text>}
        <TextField label="Reason" value={reason} onChangeText={setReason} placeholder="e.g. Review with blood test results" />
        <Button title="Save follow-up" disabled={reason.trim().length < 2 || !/^\d{4}-\d{2}-\d{2}$/.test(due)} loading={save.pending} onPress={() => void save.run()} />
      </Card>
    </View>
  );
}

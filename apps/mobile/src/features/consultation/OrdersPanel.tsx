import { useState } from 'react';
import { Text, View } from 'react-native';

import { cancelOrder, createOrder, placeOrder } from '@/api/endpoints';
import { Button, Card, ChoiceChips, SectionTitle, StatusChip, TextField } from '@/design-system/components';
import { space, useTheme, type } from '@/design-system/tokens';

import { useAction } from './useAction';
import type { EncounterData } from './useEncounterData';

export function OrdersPanel({ encId, data }: { encId: string; data: EncounterData }) {
  const t = useTheme();
  const [category, setCategory] = useState<'LAB' | 'RADIOLOGY' | 'OTHER'>('LAB');
  const [name, setName] = useState('');
  const [priority, setPriority] = useState('ROUTINE');
  const [reason, setReason] = useState('');
  const done = () => void data.refresh();
  const create = useAction(() => createOrder(encId, { category, name, priority, reason: reason || undefined }), () => { setName(''); setReason(''); done(); });
  const place = useAction(placeOrder, done);
  const cancel = useAction((id: string) => cancelOrder(id, 'Cancelled by doctor'), done);
  const orders = data.detail?.orders ?? [];
  const tone = (s: string) => (s === 'RESULTED' ? 'success' : s === 'CANCELLED' ? 'danger' : s === 'ORDERED' ? 'neutral' : 'warning');

  return (
    <View style={{ gap: space.md }}>
      <SectionTitle>Investigations</SectionTitle>
      <Card>
        {orders.length === 0 ? <Text style={{ color: t.textMuted }}>None ordered.</Text> : null}
        {orders.map((o) => (
          <View key={o.id} style={{ gap: space.xs, paddingVertical: space.xs }}>
            <Text style={{ color: t.text, fontWeight: '600' }}>{o.name}</Text>
            <View style={{ flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' }}>
              <StatusChip label={o.category.toLowerCase()} />
              <StatusChip label={o.priority.toLowerCase()} tone={o.priority === 'ROUTINE' ? 'neutral' : 'danger'} />
              <StatusChip label={o.status === 'DRAFT' ? 'Draft — not yet ordered' : o.status.toLowerCase()} tone={tone(o.status)} />
            </View>
            {o.status === 'DRAFT' ? (
              <View style={{ flexDirection: 'row', gap: space.sm }}>
                <View style={{ flex: 1 }}><Button title="Place order" loading={place.pending} onPress={() => void place.run(o.id)} /></View>
                <View style={{ flex: 1 }}><Button title="Discard" variant="secondary" onPress={() => void cancel.run(o.id)} /></View>
              </View>
            ) : null}
          </View>
        ))}
      </Card>
      <Card title="Add an investigation">
        <ChoiceChips value={category} onChange={setCategory} options={[{ value: 'LAB', label: 'Lab' }, { value: 'RADIOLOGY', label: 'Imaging' }, { value: 'OTHER', label: 'Other' }]} />
        <TextField label="Test" value={name} onChangeText={setName} placeholder="e.g. Complete blood count" />
        <ChoiceChips value={priority} onChange={setPriority} options={[{ value: 'ROUTINE', label: 'Routine' }, { value: 'URGENT', label: 'Urgent' }, { value: 'STAT', label: 'Immediate' }]} />
        <TextField label="Reason (optional)" value={reason} onChangeText={setReason} />
        <Button title="Save as draft" variant="secondary" disabled={name.trim().length < 2} loading={create.pending} onPress={() => void create.run()} />
        <Text style={[type.caption, { color: t.textMuted }]}>Nothing reaches the lab until you place the order.</Text>
      </Card>
    </View>
  );
}

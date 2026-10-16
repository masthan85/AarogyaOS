import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import { enterResult, getOrders } from '@/api/endpoints';
import type { WorklistOrder } from '@/api/schemas';
import { useAuth } from '@/auth/AuthProvider';
import { Button, Card, ChoiceChips, EmptyState, ErrorState, LoadingState, StatusChip, TextField } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
import { formatDateTime } from '@/domain/dates';
import { can } from '@/domain/permissions';
import { buildResult, byPriority, emptyResultForm, type ResultForm } from '@/domain/worklists';

function ResultEntry({ order, onDone }: { order: WorklistOrder; onDone: () => void }) {
  const t = useTheme();
  const [form, setForm] = useState<ResultForm>(emptyResultForm(order.name));
  const [error, setError] = useState<string>();
  const save = useMutation({
    mutationFn: (body: NonNullable<ReturnType<typeof buildResult>['body']>) => enterResult(order.id, body),
    onSuccess: onDone,
    onError: (e) => setError(e instanceof ApiError ? e.message : 'Could not save. Check your connection.'),
  });
  const set = (k: keyof ResultForm) => (v: string) => setForm((f) => ({ ...f, [k]: v }));
  const submit = () => {
    const { body, error: problem } = buildResult(form);
    setError(problem);
    if (body) save.mutate(body);
  };
  return (
    <View style={{ gap: space.sm }}>
      <TextField label="Test" value={form.testName} onChangeText={set('testName')} />
      <TextField label="Result" value={form.value} onChangeText={set('value')} keyboardType="default" autoCapitalize="none" />
      <TextField label="Unit" value={form.unit} onChangeText={set('unit')} autoCapitalize="none" />
      <Text style={{ color: t.textMuted, fontSize: 12 }}>
        Ranges are optional. They are used to flag the result as low, high or critical for the doctor. Leave them blank if unsure; the
        result is then marked as having no range.
      </Text>
      <TextField label="Normal range, low" value={form.refLow} onChangeText={set('refLow')} keyboardType="decimal-pad" />
      <TextField label="Normal range, high" value={form.refHigh} onChangeText={set('refHigh')} keyboardType="decimal-pad" />
      <TextField label="Critical below" value={form.criticalLow} onChangeText={set('criticalLow')} keyboardType="decimal-pad" />
      <TextField label="Critical above" value={form.criticalHigh} onChangeText={set('criticalHigh')} keyboardType="decimal-pad" />
      <TextField label="Comment (optional)" value={form.comment} onChangeText={set('comment')} multiline />
      {error ? <Text style={{ color: t.danger }}>{error}</Text> : null}
      <Button title="Save result" loading={save.isPending} onPress={submit} />
    </View>
  );
}

export function LabScreen() {
  const t = useTheme();
  const { me } = useAuth();
  const qc = useQueryClient();
  const canEnter = can(me, 'result:enter');
  const [category, setCategory] = useState<'LAB' | 'RADIOLOGY'>('LAB');
  const [open, setOpen] = useState<string>();
  const q = useQuery({
    queryKey: ['orders-worklist', category],
    queryFn: () => getOrders({ status: 'ORDERED', category }),
    gcTime: 0,
    refetchInterval: 30_000,
  });
  const done = () => {
    setOpen(undefined);
    void qc.invalidateQueries({ queryKey: ['orders-worklist'] });
    Alert.alert('Result saved', 'The ordering doctor will see it for review.');
  };

  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md }} keyboardShouldPersistTaps="handled">
      <ChoiceChips
        value={category}
        onChange={(c) => { setCategory(c); setOpen(undefined); }}
        options={[{ value: 'LAB', label: 'Laboratory' }, { value: 'RADIOLOGY', label: 'Radiology' }]}
      />
      {q.isPending ? <LoadingState label="Loading orders…" /> : null}
      {q.isError ? <ErrorState message="Could not load orders." onRetry={() => void q.refetch()} /> : null}
      {q.data?.length === 0 ? <EmptyState message="No orders waiting for a result." /> : null}
      {q.data
        ? byPriority(q.data).map((o) => (
            <Card key={o.id} title={o.name}>
              <View style={{ flexDirection: 'row', gap: space.sm }}>
                <StatusChip label={o.priority.toLowerCase()} tone={o.priority === 'ROUTINE' ? 'neutral' : 'danger'} />
              </View>
              <Text style={{ color: t.text }}>{o.patient_name ?? 'Patient'} · {o.patient_mrn ?? ''}</Text>
              {o.reason ? <Text style={{ color: t.textMuted }}>Reason: {o.reason}</Text> : null}
              {o.ordered_at ? <Text style={{ color: t.textMuted, fontSize: 12 }}>Ordered {formatDateTime(o.ordered_at)}</Text> : null}
              {canEnter ? (
                open === o.id ? (
                  <ResultEntry order={o} onDone={done} />
                ) : (
                  <Button title="Enter result" variant="secondary" onPress={() => setOpen(o.id)} />
                )
              ) : null}
            </Card>
          ))
        : null}
    </ScrollView>
  );
}

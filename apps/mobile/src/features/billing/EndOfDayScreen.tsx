import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import { closeDay, getDay } from '@/api/endpoints';
import { Button, Card, ErrorState, Lead, LoadingState, TextField } from '@/design-system/components';
import { space, type, useTheme } from '@/design-system/tokens';
import { formatRupees, METHOD_LABELS, parseRupees } from '@/domain/billing';
import { isoToday } from '@/domain/history';

export function EndOfDayScreen() {
  const t = useTheme();
  const today = isoToday();
  const q = useQuery({ queryKey: ['billing-day', today], queryFn: () => getDay(today), gcTime: 0 });
  const [counted, setCounted] = useState('');
  const [note, setNote] = useState('');
  const paise = parseRupees(counted);
  const close = useMutation({
    mutationFn: () => closeDay({ business_date: today, counted_cash_paise: paise as number, note: note.trim() || undefined }),
    onSuccess: () => void q.refetch(),
    onError: (e) => Alert.alert('Could not close the day', e instanceof ApiError ? e.message : 'Check your connection.'),
  });
  if (q.isPending) return <LoadingState />;
  if (q.isError || !q.data) return <ErrorState message="Could not load today's takings." onRetry={() => void q.refetch()} />;
  const d = q.data;
  const diff = paise === null ? null : paise - d.expected_cash_paise;
  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md }} keyboardShouldPersistTaps="handled">
      <Lead>Money received and refunded today, counted in India time. Count the cash in the drawer and compare.</Lead>
      <Card title="Today">
        {d.by_method.length === 0 ? <Text style={{ color: t.textMuted }}>No payments or refunds yet today.</Text> : null}
        {d.by_method.map((m) => (
          <View key={m.method} style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <Text style={[type.body, { color: t.text }]}>{METHOD_LABELS[m.method] ?? m.method}</Text>
            <Text style={[type.body, { color: t.text, fontVariant: ['tabular-nums'] }]}>
              {formatRupees(m.net_paise)}{m.refunded_paise > 0 ? ` (after ${formatRupees(m.refunded_paise)} refunded)` : ''}
            </Text>
          </View>
        ))}
        <Text style={[type.title, { color: t.text }]}>Net {formatRupees(d.net_paise)}</Text>
      </Card>
      {d.closing ? (
        <Card title="Day closed">
          <Text style={[type.body, { color: t.text }]}>Expected cash {formatRupees(d.closing.expected_cash_paise)} · counted {formatRupees(d.closing.counted_cash_paise)}</Text>
          <Text style={[type.body, { color: d.closing.difference_paise === 0 ? t.success : t.warning, fontWeight: '700' }]}>
            {d.closing.difference_paise === 0 ? 'Cash matches' : d.closing.difference_paise > 0 ? `${formatRupees(d.closing.difference_paise)} more than expected` : `${formatRupees(-d.closing.difference_paise)} short`}
          </Text>
          {d.closing.note ? <Text style={[type.small, { color: t.textMuted }]}>{d.closing.note}</Text> : null}
        </Card>
      ) : (
        <Card title="Close the day">
          <Text style={[type.body, { color: t.text }]}>Cash expected in the drawer: {formatRupees(d.expected_cash_paise)}</Text>
          <TextField label="Cash counted (₹)" keyboardType="decimal-pad" value={counted} onChangeText={setCounted} />
          {diff !== null && diff !== 0 ? <Text style={[type.small, { color: t.warning }]}>{diff > 0 ? `${formatRupees(diff)} more` : `${formatRupees(-diff)} short`} than expected. Add a note if you know why.</Text> : null}
          <TextField label="Note (optional)" value={note} onChangeText={setNote} />
          <Button title="Close the day" loading={close.isPending} disabled={paise === null} onPress={() => Alert.alert('Close today?', 'It is recorded once and cannot be changed.', [{ text: 'Not yet', style: 'cancel' }, { text: 'Close', onPress: () => close.mutate() }])} />
        </Card>
      )}
    </ScrollView>
  );
}

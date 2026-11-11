import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Alert, ScrollView, Text } from 'react-native';

import { ApiError } from '@/api/client';
import { addPrice, getBillingSettings, getPrices, saveBillingSettings, updatePrice } from '@/api/endpoints';
import { Button, Card, EmptyState, ErrorState, Lead, LoadingState, SectionTitle, TextField } from '@/design-system/components';
import { space, type, useTheme } from '@/design-system/tokens';
import { formatRupees, parsePercent, parseRupees, percentLabel } from '@/domain/billing';

const fail = (title: string) => (e: unknown) => Alert.alert(title, e instanceof ApiError ? e.message : 'Check your connection.');
const GSTIN = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;

function Settings() {
  const t = useTheme();
  const q = useQuery({ queryKey: ['billing-settings'], queryFn: getBillingSettings, gcTime: 0 });
  const [gstin, setGstin] = useState('');
  const [name, setName] = useState('');
  useEffect(() => { if (q.data) { setGstin(q.data.gstin ?? ''); setName(q.data.legal_name ?? ''); } }, [q.data]);
  const g = gstin.trim().toUpperCase();
  const bad = g !== '' && !GSTIN.test(g);
  const save = useMutation({
    mutationFn: () => saveBillingSettings({ gstin: g || null, legal_name: name.trim() || null }),
    onSuccess: () => void q.refetch(),
    onError: fail('Could not save'),
  });
  if (q.isPending) return <LoadingState />;
  return (
    <Card title="GSTIN">
      <Text style={[type.small, { color: t.textMuted }]}>Printed on invoices issued from now on. Leave it empty if the clinic is not registered. Invoices already issued keep the number they were issued with.</Text>
      <TextField label="GSTIN" autoCapitalize="characters" maxLength={15} value={gstin} onChangeText={setGstin} error={bad ? 'A GSTIN has 15 characters, for example 29ABCDE1234F1Z5' : undefined} />
      <TextField label="Name for invoices (optional)" value={name} onChangeText={setName} />
      <Button title="Save" disabled={bad} loading={save.isPending} onPress={() => save.mutate()} />
    </Card>
  );
}

export function PriceListScreen() {
  const t = useTheme();
  const qc = useQueryClient();
  const prices = useQuery({ queryKey: ['prices', 'all'], queryFn: () => getPrices(true), gcTime: 0 });
  const [name, setName] = useState('');
  const [price, setPrice] = useState('');
  const [tax, setTax] = useState('0');
  const paise = parseRupees(price);
  const rate = parsePercent(tax);
  const refresh = () => { void qc.invalidateQueries({ queryKey: ['prices'] }); };
  const add = useMutation({
    mutationFn: () => addPrice({ name: name.trim(), price_paise: paise as number, tax_rate_bp: rate as number }),
    onSuccess: () => { setName(''); setPrice(''); setTax('0'); refresh(); },
    onError: fail('Could not add the service'),
  });
  const toggle = useMutation({
    mutationFn: (v: { id: string; active: boolean }) => updatePrice(v.id, { active: v.active }),
    onSuccess: refresh,
    onError: fail('Could not update the service'),
  });
  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md, width: '100%', maxWidth: 720, alignSelf: 'center' }} keyboardShouldPersistTaps="handled">
      <Lead>Services you charge for often. They appear as quick buttons on a new invoice. Changing a price never changes an invoice already issued.</Lead>
      <SectionTitle>Services</SectionTitle>
      {prices.isPending ? <LoadingState /> : null}
      {prices.isError ? <ErrorState message="Could not load the price list." onRetry={() => void prices.refetch()} /> : null}
      {prices.data?.length === 0 ? <EmptyState title="No services yet" message="Add the first one below." /> : null}
      {prices.data?.map((p) => (
        <Card key={p.id}>
          <Text style={[type.h3, { color: p.active ? t.text : t.textMuted }]}>{p.name}</Text>
          <Text style={[type.small, { color: t.textMuted }]}>{formatRupees(p.price_paise)}{p.tax_rate_bp > 0 ? ` + ${percentLabel(p.tax_rate_bp)} tax` : ''}{p.active ? '' : ' · hidden'}</Text>
          <Button size="sm" variant="ghost" title={p.active ? 'Hide from new invoices' : 'Show again'} onPress={() => toggle.mutate({ id: p.id, active: !p.active })} />
        </Card>
      ))}
      <Card title="Add a service">
        <TextField label="Name" placeholder="e.g. Chest X-ray" value={name} onChangeText={setName} />
        <TextField label="Price (₹)" keyboardType="decimal-pad" value={price} onChangeText={setPrice} />
        <TextField label="Tax %" keyboardType="decimal-pad" value={tax} onChangeText={setTax} error={rate === null ? 'Enter 0 to 28' : undefined} />
        <Button title="Add to price list" loading={add.isPending} disabled={name.trim().length < 2 || paise === null || rate === null} onPress={() => add.mutate()} />
      </Card>
      <Settings />
    </ScrollView>
  );
}

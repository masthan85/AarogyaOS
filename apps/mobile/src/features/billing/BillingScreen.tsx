import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, Pressable, ScrollView, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import { createInvoice, getInvoices, getToBill } from '@/api/endpoints';
import type { Invoice } from '@/api/schemas';
import { useAuth } from '@/auth/AuthProvider';
import { Button, Card, EmptyState, ErrorState, Lead, LoadingState, StatusChip, TabBar } from '@/design-system/components';
import { space, type, useTheme } from '@/design-system/tokens';
import { formatRupees, invoiceState } from '@/domain/billing';
import { formatDateTime } from '@/domain/dates';
import { can } from '@/domain/permissions';
import { PatientSearchScreen } from '@/features/patients/PatientSearchScreen';

type Tab = 'tobill' | 'unpaid' | 'recent';

function InvoiceRow({ inv }: { inv: Invoice }) {
  const t = useTheme();
  const state = invoiceState(inv);
  return (
    <Pressable accessibilityRole="button" onPress={() => router.push(`/billing/${inv.id}`)}>
      <Card>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: space.sm }}>
          <Text style={[type.h3, { color: t.text }]}>{inv.number ?? 'Draft'}</Text>
          <StatusChip label={state.label} tone={state.tone} />
        </View>
        <Text style={[type.body, { color: t.text }]}>{inv.patient_name} <Text style={{ color: t.textMuted }}>· {inv.patient_mrn}</Text></Text>
        <Text style={[type.small, { color: t.textMuted }]}>
          {formatRupees(inv.total_paise)}
          {inv.status === 'ISSUED' && inv.balance_paise > 0 ? ` · ${formatRupees(inv.balance_paise)} due` : ''}
          {' · '}{formatDateTime(inv.issued_at ?? inv.created_at)}
        </Text>
      </Card>
    </Pressable>
  );
}

export function BillingScreen() {
  const t = useTheme();
  const { me } = useAuth();
  const qc = useQueryClient();
  const canWrite = can(me, 'billing:write');
  const [tab, setTab] = useState<Tab>(canWrite ? 'tobill' : 'unpaid');
  const [picking, setPicking] = useState(false);
  const toBill = useQuery({ queryKey: ['to-bill'], queryFn: getToBill, enabled: canWrite && tab === 'tobill', gcTime: 0 });
  const invoices = useQuery({
    queryKey: ['invoices', tab],
    queryFn: () => getInvoices({ unpaid: tab === 'unpaid' }),
    enabled: tab !== 'tobill',
    gcTime: 0,
  });
  const start = useMutation({
    mutationFn: (body: { patient_id: string; encounter_id?: string }) => createInvoice(body),
    onSuccess: (inv) => {
      void qc.invalidateQueries({ queryKey: ['to-bill'] });
      router.push(`/billing/${inv.id}`);
    },
    onError: (e) => Alert.alert('Could not start the invoice', e instanceof ApiError ? e.message : 'Check your connection.'),
  });

  if (picking) {
    return (
      <View style={{ flex: 1 }}>
        <View style={{ padding: space.md, paddingBottom: 0 }}>
          <Lead>Choose the patient to invoice. This is for a charge that is not tied to a finished visit.</Lead>
        </View>
        <PatientSearchScreen onSelect={(p) => { setPicking(false); start.mutate({ patient_id: p.id }); }} />
        <View style={{ padding: space.md }}><Button title="Cancel" variant="ghost" onPress={() => setPicking(false)} /></View>
      </View>
    );
  }

  const tabs = [...(canWrite ? [{ value: 'tobill' as const, label: 'To bill' }] : []), { value: 'unpaid' as const, label: 'Unpaid' }, { value: 'recent' as const, label: 'Recent' }];
  return (
    <View style={{ flex: 1 }}>
      <TabBar tabs={tabs} value={tab} onChange={setTab} />
      <ScrollView contentContainerStyle={{ padding: space.md, gap: space.sm }}>
        {tab === 'tobill' ? (
          <>
            <Lead>Visits finished in the last 7 days with no invoice yet.</Lead>
            {toBill.isPending ? <LoadingState /> : null}
            {toBill.isError ? <ErrorState message="Could not load visits." onRetry={() => void toBill.refetch()} /> : null}
            {toBill.data?.length === 0 ? <EmptyState title="Nothing to bill" message="Every recent visit has an invoice." /> : null}
            {toBill.data?.map((v) => (
              <Card key={v.encounter_id}>
                <Text style={[type.h3, { color: t.text }]}>{v.patient_name}</Text>
                <Text style={[type.small, { color: t.textMuted }]}>
                  {v.patient_mrn}{v.practitioner_name ? ` · ${v.practitioner_name}` : ''}{v.ended_at ? ` · finished ${formatDateTime(v.ended_at)}` : ''}
                </Text>
                <Button size="sm" title="Start invoice" loading={start.isPending} onPress={() => start.mutate({ patient_id: v.patient_id, encounter_id: v.encounter_id })} />
              </Card>
            ))}
            <Button title="Invoice another patient" variant="secondary" onPress={() => setPicking(true)} />
            <Button title="End of day" variant="ghost" onPress={() => router.push('/billing/day')} />
            {can(me, 'billing:manage') ? <Button title="Price list and GSTIN" variant="ghost" onPress={() => router.push('/billing/prices')} /> : null}
          </>
        ) : (
          <>
            {invoices.isPending ? <LoadingState /> : null}
            {invoices.isError ? <ErrorState message="Could not load invoices." onRetry={() => void invoices.refetch()} /> : null}
            {invoices.data?.length === 0 ? (
              <EmptyState title={tab === 'unpaid' ? 'Nothing unpaid' : 'No invoices yet'} message={tab === 'unpaid' ? 'Every issued invoice is paid.' : 'Invoices appear here once started.'} />
            ) : null}
            {invoices.data?.map((inv) => <InvoiceRow key={inv.id} inv={inv} />)}
            {!canWrite && can(me, 'billing:manage') ? <Button title="Price list and GSTIN" variant="ghost" onPress={() => router.push('/billing/prices')} /> : null}
          </>
        )}
      </ScrollView>
    </View>
  );
}

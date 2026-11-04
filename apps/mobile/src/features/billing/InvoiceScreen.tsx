import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import { getInvoice, getOrganisation, issueInvoice, payInvoice, setInvoiceLines, voidInvoice, type PaymentMethod } from '@/api/endpoints';
import type { Invoice } from '@/api/schemas';
import { useAuth } from '@/auth/AuthProvider';
import { AlertBanner, Button, Card, ChoiceChips, ErrorState, LoadingState, SectionTitle, StatusChip, TextField } from '@/design-system/components';
import { space, type, useTheme } from '@/design-system/tokens';
import { draftTotal, emptyLine, formatRupees, invoiceState, METHOD_LABELS, parseLines, parseRupees, type LineDraft } from '@/domain/billing';
import { formatDateTime } from '@/domain/dates';
import { can } from '@/domain/permissions';
import { invoiceHtml } from '@/domain/print';
import { printHtml, sharePdf } from '@/services/print';

const fail = (title: string) => (e: unknown) => Alert.alert(title, e instanceof ApiError ? e.message : 'Check your connection.');

function Totals({ inv, total }: { inv: Invoice; total: number }) {
  const t = useTheme();
  return (
    <View style={{ gap: 2 }}>
      <Text style={[type.title, { color: t.text }]}>Total {formatRupees(total)}</Text>
      {inv.status === 'ISSUED' ? (
        <Text style={[type.body, { color: inv.balance_paise > 0 ? t.warning : t.success, fontWeight: '700' }]}>
          {inv.balance_paise > 0 ? `${formatRupees(inv.balance_paise)} still due` : 'Paid in full'}
          {inv.paid_paise > 0 && inv.balance_paise > 0 ? ` (${formatRupees(inv.paid_paise)} received)` : ''}
        </Text>
      ) : null}
    </View>
  );
}

function DraftEditor({ inv, onChanged }: { inv: Invoice; onChanged: () => void }) {
  const t = useTheme();
  const toDraft = (l: Invoice['lines'][number]): LineDraft => ({
    description: l.description,
    quantity: String(l.quantity),
    price: String(l.unit_price_paise / 100),
  });
  const [rows, setRows] = useState<LineDraft[]>(inv.lines.length ? inv.lines.map(toDraft) : [emptyLine()]);
  const [error, setError] = useState<string>();
  const parsed = parseLines(rows);
  const save = useMutation({
    mutationFn: () => setInvoiceLines(inv.id, parsed.lines),
    onSuccess: onChanged,
    onError: fail('Could not save the charges'),
  });
  const issue = useMutation({
    mutationFn: async () => {
      await setInvoiceLines(inv.id, parsed.lines);
      return issueInvoice(inv.id);
    },
    onSuccess: onChanged,
    onError: fail('Could not issue the invoice'),
  });
  const discard = useMutation({
    mutationFn: () => voidInvoice(inv.id, 'Draft discarded'),
    onSuccess: () => router.back(),
    onError: fail('Could not discard the draft'),
  });
  const set = (i: number, patch: Partial<LineDraft>) => setRows((r) => r.map((x, k) => (k === i ? { ...x, ...patch } : x)));
  const check = (go: () => void) => {
    setError(parsed.error);
    if (!parsed.error) go();
  };

  return (
    <View style={{ gap: space.md }}>
      <SectionTitle>Charges</SectionTitle>
      {rows.map((r, i) => (
        <Card key={i}>
          <TextField label={`Charge ${i + 1}`} placeholder="e.g. Consultation" value={r.description} onChangeText={(v) => set(i, { description: v })} />
          <View style={{ flexDirection: 'row', gap: space.md }}>
            <View style={{ flex: 1 }}><TextField label="Quantity" keyboardType="number-pad" value={r.quantity} onChangeText={(v) => set(i, { quantity: v })} /></View>
            <View style={{ flex: 2 }}><TextField label="Amount each (₹)" keyboardType="decimal-pad" value={r.price} onChangeText={(v) => set(i, { price: v })} /></View>
          </View>
          {rows.length > 1 ? <Button size="sm" title="Remove this charge" variant="ghost" onPress={() => setRows((x) => x.filter((_, k) => k !== i))} /> : null}
        </Card>
      ))}
      <Button title="Add a charge" variant="secondary" onPress={() => setRows((r) => [...r, emptyLine()])} />
      <Text style={[type.title, { color: t.text }]}>Total {formatRupees(draftTotal(parsed.lines))}</Text>
      {error ? <AlertBanner level="WARNING" message={error} /> : null}
      <Text style={[type.small, { color: t.textMuted }]}>
        Enter the amounts exactly as they should appear. Tax is not calculated here. After you issue the invoice it cannot be edited, only voided.
      </Text>
      <Button title="Save charges" variant="secondary" loading={save.isPending} onPress={() => check(() => save.mutate())} />
      <Button
        title="Issue invoice"
        loading={issue.isPending}
        disabled={parsed.lines.length === 0}
        onPress={() => check(() => Alert.alert('Issue this invoice?', `Total ${formatRupees(draftTotal(parsed.lines))}. It cannot be edited afterwards.`, [{ text: 'Not yet', style: 'cancel' }, { text: 'Issue', onPress: () => issue.mutate() }]))}
      />
      <Button title="Discard draft" variant="ghost" loading={discard.isPending} onPress={() => Alert.alert('Discard this draft?', 'It will be deleted.', [{ text: 'Keep', style: 'cancel' }, { text: 'Discard', style: 'destructive', onPress: () => discard.mutate() }])} />
    </View>
  );
}

function IssuedView({ inv, canWrite, onChanged }: { inv: Invoice; canWrite: boolean; onChanged: () => void }) {
  const t = useTheme();
  const org = useQuery({ queryKey: ['organisation'], queryFn: getOrganisation });
  const [amount, setAmount] = useState(String(inv.balance_paise / 100));
  const [method, setMethod] = useState<PaymentMethod>('CASH');
  const [reference, setReference] = useState('');
  const [reason, setReason] = useState('');
  const [voiding, setVoiding] = useState(false);
  useEffect(() => setAmount(String(inv.balance_paise / 100)), [inv.balance_paise]);
  const paise = parseRupees(amount);
  const pay = useMutation({
    mutationFn: () => payInvoice(inv.id, { amount_paise: paise as number, method, reference: reference.trim() || undefined }),
    onSuccess: () => { setReference(''); onChanged(); },
    onError: fail('Could not record the payment'),
  });
  const cancel = useMutation({ mutationFn: () => voidInvoice(inv.id, reason.trim()), onSuccess: onChanged, onError: fail('Could not void the invoice') });
  const html = invoiceHtml(inv, org.data?.name ?? 'Clinic');

  return (
    <View style={{ gap: space.md }}>
      <Card>
        {inv.lines.map((l, i) => (
          <View key={i} style={{ flexDirection: 'row', justifyContent: 'space-between', gap: space.sm }}>
            <Text style={[type.body, { color: t.text, flex: 1 }]}>{l.description}{l.quantity > 1 ? ` × ${l.quantity}` : ''}</Text>
            <Text style={[type.body, { color: t.text, fontVariant: ['tabular-nums'] }]}>{formatRupees(l.total_paise)}</Text>
          </View>
        ))}
        <Totals inv={inv} total={inv.total_paise} />
      </Card>
      {inv.payments.length > 0 ? (
        <Card title="Payments received">
          {inv.payments.map((p) => (
            <Text key={p.id} style={[type.small, { color: t.text }]}>
              {formatDateTime(p.received_at)} · {formatRupees(p.amount_paise)} · {METHOD_LABELS[p.method] ?? p.method}{p.reference ? ` · ${p.reference}` : ''}
            </Text>
          ))}
        </Card>
      ) : null}
      {canWrite && inv.balance_paise > 0 ? (
        <Card title="Record a payment">
          <TextField label="Amount received (₹)" keyboardType="decimal-pad" value={amount} onChangeText={setAmount} />
          <ChoiceChips value={method} onChange={setMethod} options={(['CASH', 'UPI', 'CARD', 'OTHER'] as const).map((m) => ({ value: m, label: METHOD_LABELS[m] }))} />
          <TextField label="Reference (optional)" placeholder="UPI or card receipt number" value={reference} onChangeText={setReference} />
          {paise === null ? <Text style={[type.small, { color: t.warning }]}>Enter the amount in rupees, for example 500 or 499.50.</Text> : null}
          {paise !== null && paise > inv.balance_paise ? <Text style={[type.small, { color: t.warning }]}>That is more than the {formatRupees(inv.balance_paise)} still due.</Text> : null}
          <Button title="Record payment" loading={pay.isPending} disabled={paise === null || paise <= 0 || paise > inv.balance_paise} onPress={() => pay.mutate()} />
        </Card>
      ) : null}
      {html ? (
        <View style={{ flexDirection: 'row', gap: space.sm }}>
          <View style={{ flex: 1 }}><Button title="Share as PDF" variant="secondary" onPress={() => void sharePdf(html, `Invoice ${inv.number}`)} /></View>
          <View style={{ flex: 1 }}><Button title="Print" variant="secondary" onPress={() => void printHtml(html)} /></View>
        </View>
      ) : null}
      {canWrite && inv.paid_paise === 0 ? (
        voiding ? (
          <Card title="Void this invoice">
            <Text style={[type.small, { color: t.textMuted }]}>The invoice stays on record as void and the visit can be billed again.</Text>
            <TextField label="Why is it being voided?" value={reason} onChangeText={setReason} />
            <Button title="Void invoice" variant="danger" disabled={reason.trim().length < 3} loading={cancel.isPending} onPress={() => cancel.mutate()} />
            <Button title="Keep it" variant="ghost" onPress={() => setVoiding(false)} />
          </Card>
        ) : (
          <Button title="Void invoice" variant="ghost" onPress={() => setVoiding(true)} />
        )
      ) : null}
      {canWrite && inv.paid_paise > 0 ? <Text style={[type.caption, { color: t.textMuted }]}>Money has been received, so this invoice cannot be voided. Refunds are not built yet.</Text> : null}
    </View>
  );
}

export function InvoiceScreen() {
  const t = useTheme();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { me } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['invoice', id], queryFn: () => getInvoice(id), gcTime: 0 });
  const changed = () => {
    void qc.invalidateQueries({ queryKey: ['invoice', id] });
    void qc.invalidateQueries({ queryKey: ['invoices'] });
    void qc.invalidateQueries({ queryKey: ['to-bill'] });
  };
  if (q.isPending) return <LoadingState label="Opening invoice…" />;
  if (q.isError || !q.data) return <ErrorState message="Could not open this invoice." onRetry={() => void q.refetch()} />;
  const inv = q.data;
  const state = invoiceState(inv);
  const canWrite = can(me, 'billing:write');
  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md }} keyboardShouldPersistTaps="handled">
      <View style={{ gap: space.xs }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: space.sm }}>
          <Text style={[type.title, { color: t.text }]}>{inv.number ?? 'Draft invoice'}</Text>
          <StatusChip label={state.label} tone={state.tone} />
        </View>
        <Text style={[type.body, { color: t.text }]}>{inv.patient_name} <Text style={{ color: t.textMuted }}>· {inv.patient_mrn}</Text></Text>
      </View>
      {inv.status === 'VOID' ? <AlertBanner level="WARNING" message={`Voided: ${inv.void_reason ?? ''}`} /> : null}
      {inv.status === 'DRAFT' && canWrite ? <DraftEditor inv={inv} onChanged={changed} /> : null}
      {inv.status === 'DRAFT' && !canWrite ? <Text style={[type.small, { color: t.textMuted }]}>This invoice is still a draft.</Text> : null}
      {inv.status !== 'DRAFT' ? <IssuedView inv={inv} canWrite={canWrite && inv.status === 'ISSUED'} onChanged={changed} /> : null}
    </ScrollView>
  );
}

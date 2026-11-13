import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import { addClaim, creditInvoice, getClaims, getInvoice, getOrganisation, getPrices, issueInvoice, payInvoice, refundInvoice, setInvoiceLines, updateClaim, voidInvoice, type PaymentMethod } from '@/api/endpoints';
import type { Invoice } from '@/api/schemas';
import { useAuth } from '@/auth/AuthProvider';
import { AlertBanner, Button, Card, ChoiceChips, ErrorState, LoadingState, SectionTitle, StatusChip, TextField } from '@/design-system/components';
import { space, type, useTheme } from '@/design-system/tokens';
import { draftTotals, emptyLine, formatRupees, invoiceState, METHOD_LABELS, parseLines, parseRupees, percentLabel, type LineDraft } from '@/domain/billing';
import { formatDateTime } from '@/domain/dates';
import { can } from '@/domain/permissions';
import { invoiceHtml } from '@/domain/print';
import { printHtml, sharePdf } from '@/services/print';

const fail = (title: string) => (e: unknown) => Alert.alert(title, e instanceof ApiError ? e.message : 'Check your connection.');

function Totals({ inv, total }: { inv: Invoice; total: number }) {
  const t = useTheme();
  return (
    <View style={{ gap: 2 }}>
      {inv.tax_paise > 0 ? <Text style={[type.small, { color: t.textMuted }]}>Includes tax {formatRupees(inv.tax_paise)}</Text> : null}
      <Text style={[type.title, { color: t.text }]}>Total {formatRupees(total)}</Text>
      {inv.credited_paise > 0 ? <Text style={[type.body, { color: t.text }]}>Credit notes -{formatRupees(inv.credited_paise)} · Net {formatRupees(inv.net_paise)}</Text> : null}
      {inv.refund_due_paise > 0 ? <Text style={[type.body, { color: t.warning, fontWeight: '700' }]}>{formatRupees(inv.refund_due_paise)} paid beyond what is owed: refund it or leave it as credit</Text> : null}
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
    taxPct: String(l.tax_rate_bp / 100),
  });
  const [rows, setRows] = useState<LineDraft[]>(inv.lines.length ? inv.lines.map(toDraft) : [emptyLine()]);
  const [error, setError] = useState<string>();
  const parsed = parseLines(rows);
  const prices = useQuery({ queryKey: ['prices'], queryFn: () => getPrices(), gcTime: 0 });
  const totals = draftTotals(parsed.lines);
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
      {prices.data && prices.data.length > 0 ? (
        <Card title="Add from the price list">
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
            {prices.data.map((p) => (
              <Button key={p.id} size="sm" variant="secondary" title={`${p.name} · ${formatRupees(p.price_paise)}`}
                onPress={() => setRows((r) => [...r.filter((x) => x.description.trim() || x.price.trim()), { description: p.name, quantity: '1', price: String(p.price_paise / 100), taxPct: String(p.tax_rate_bp / 100) }])} />
            ))}
          </View>
        </Card>
      ) : null}
      {rows.map((r, i) => (
        <Card key={i}>
          <TextField label={`Charge ${i + 1}`} placeholder="e.g. Consultation" value={r.description} onChangeText={(v) => set(i, { description: v })} />
          <View style={{ flexDirection: 'row', gap: space.md }}>
            <View style={{ flex: 1 }}><TextField label="Quantity" keyboardType="number-pad" value={r.quantity} onChangeText={(v) => set(i, { quantity: v })} /></View>
            <View style={{ flex: 2 }}><TextField label="Amount each (₹)" keyboardType="decimal-pad" value={r.price} onChangeText={(v) => set(i, { price: v })} /></View>
            <View style={{ flex: 1 }}><TextField label="Tax %" keyboardType="decimal-pad" value={r.taxPct} onChangeText={(v) => set(i, { taxPct: v })} /></View>
          </View>
          {rows.length > 1 ? <Button size="sm" title="Remove this charge" variant="ghost" onPress={() => setRows((x) => x.filter((_, k) => k !== i))} /> : null}
        </Card>
      ))}
      <Button title="Add a charge" variant="secondary" onPress={() => setRows((r) => [...r, emptyLine()])} />
      {totals.tax > 0 ? <Text style={[type.small, { color: t.textMuted }]}>Tax {formatRupees(totals.tax)}</Text> : null}
      <Text style={[type.title, { color: t.text }]}>Total {formatRupees(totals.total)}</Text>
      {error ? <AlertBanner level="WARNING" message={error} /> : null}
      <Text style={[type.small, { color: t.textMuted }]}>
        Enter each tax rate yourself (leave it at 0 where no tax applies); the app only adds up what you enter, so check the rates with your accountant. After you issue the invoice it cannot be edited, only voided.
      </Text>
      <Button title="Save charges" variant="secondary" loading={save.isPending} onPress={() => check(() => save.mutate())} />
      <Button
        title="Issue invoice"
        loading={issue.isPending}
        disabled={parsed.lines.length === 0}
        onPress={() => check(() => Alert.alert('Issue this invoice?', `Total ${formatRupees(totals.total)}. It cannot be edited afterwards.`, [{ text: 'Not yet', style: 'cancel' }, { text: 'Issue', onPress: () => issue.mutate() }]))}
      />
      <Button title="Discard draft" variant="ghost" loading={discard.isPending} onPress={() => Alert.alert('Discard this draft?', 'It will be deleted.', [{ text: 'Keep', style: 'cancel' }, { text: 'Discard', style: 'destructive', onPress: () => discard.mutate() }])} />
    </View>
  );
}

function Adjustments({ inv, onChanged }: { inv: Invoice; onChanged: () => void }) {
  const t = useTheme();
  const [mode, setMode] = useState<'credit' | 'refund' | null>(null);
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [method, setMethod] = useState<PaymentMethod>('CASH');
  const paise = parseRupees(amount);
  const limit = mode === 'credit' ? inv.net_paise : inv.refund_due_paise;
  const done = () => { setMode(null); setAmount(''); setReason(''); onChanged(); };
  const send = useMutation({
    mutationFn: () => (mode === 'credit' ? creditInvoice(inv.id, { amount_paise: paise as number, reason: reason.trim() }) : refundInvoice(inv.id, { amount_paise: paise as number, method, reason: reason.trim() })),
    onSuccess: done,
    onError: fail(mode === 'credit' ? 'Could not issue the credit note' : 'Could not record the refund'),
  });
  if (!mode) {
    return (
      <View style={{ gap: space.sm }}>
        {inv.net_paise > 0 ? <Button title="Issue a credit note" variant="secondary" onPress={() => { setMode('credit'); setAmount(''); }} /> : null}
        {inv.refund_due_paise > 0 ? <Button title="Refund money" variant="secondary" onPress={() => { setMode('refund'); setAmount(String(inv.refund_due_paise / 100)); }} /> : null}
      </View>
    );
  }
  return (
    <Card title={mode === 'credit' ? 'Credit note' : 'Refund'}>
      <Text style={[type.small, { color: t.textMuted }]}>
        {mode === 'credit' ? `Lowers what this invoice is worth, up to ${formatRupees(inv.net_paise)}. It cannot be undone.` : `Hands back money paid beyond what is owed, up to ${formatRupees(inv.refund_due_paise)}.`}
      </Text>
      <TextField label="Amount (₹)" keyboardType="decimal-pad" value={amount} onChangeText={setAmount} />
      {mode === 'refund' ? <ChoiceChips value={method} onChange={setMethod} options={(['CASH', 'UPI', 'CARD', 'OTHER'] as const).map((m) => ({ value: m, label: METHOD_LABELS[m] }))} /> : null}
      <TextField label="Reason" value={reason} onChangeText={setReason} />
      {paise !== null && paise > limit ? <Text style={[type.small, { color: t.warning }]}>That is more than {formatRupees(limit)}.</Text> : null}
      <Button title={mode === 'credit' ? 'Issue credit note' : 'Record refund'} loading={send.isPending} disabled={paise === null || paise <= 0 || paise > limit || reason.trim().length < 3}
        onPress={() => Alert.alert(mode === 'credit' ? 'Issue this credit note?' : 'Record this refund?', `${formatRupees(paise ?? 0)} · it stays on the record.`, [{ text: 'Not yet', style: 'cancel' }, { text: 'Yes', onPress: () => send.mutate() }])} />
      <Button title="Cancel" variant="ghost" onPress={() => setMode(null)} />
    </Card>
  );
}

const CLAIM_LABELS: Record<string, string> = { SUBMITTED: 'Submitted', APPROVED: 'Approved', PART_APPROVED: 'Part approved', REJECTED: 'Rejected', SETTLED: 'Settled' };

function Claims({ inv }: { inv: Invoice }) {
  const t = useTheme();
  const qc = useQueryClient();
  const claims = useQuery({ queryKey: ['claims', inv.id], queryFn: () => getClaims(inv.id), gcTime: 0 });
  const [adding, setAdding] = useState(false);
  const [insurer, setInsurer] = useState('');
  const [policy, setPolicy] = useState('');
  const [amount, setAmount] = useState(String(inv.net_paise / 100));
  const [approved, setApproved] = useState<Record<string, string>>({});
  const paise = parseRupees(amount);
  const refresh = () => void qc.invalidateQueries({ queryKey: ['claims', inv.id] });
  const create = useMutation({
    mutationFn: () => addClaim(inv.id, { insurer: insurer.trim(), claimed_paise: paise as number, policy_number: policy.trim() || undefined }),
    onSuccess: () => { setAdding(false); setInsurer(''); setPolicy(''); refresh(); },
    onError: fail('Could not save the claim'),
  });
  const move = useMutation({
    mutationFn: (v: { id: string; status: string; approved?: number }) => updateClaim(v.id, { status: v.status, approved_paise: v.approved }),
    onSuccess: refresh,
    onError: fail('Could not update the claim'),
  });
  return (
    <Card title="Insurance claims">
      <Text style={[type.caption, { color: t.textMuted }]}>This only keeps track. Nothing is sent to an insurer from here. When money arrives, record it as a payment from the insurer.</Text>
      {claims.data?.length === 0 ? <Text style={{ color: t.textMuted }}>No claims on this invoice.</Text> : null}
      {claims.data?.map((c) => {
        const open = c.status !== 'REJECTED' && c.status !== 'SETTLED';
        const amt = parseRupees(approved[c.id] ?? '');
        return (
          <View key={c.id} style={{ gap: space.xs, paddingVertical: space.xs }}>
            <Text style={{ color: t.text, fontWeight: '600' }}>{c.insurer} · {formatRupees(c.claimed_paise)}</Text>
            <Text style={[type.small, { color: t.textMuted }]}>{CLAIM_LABELS[c.status] ?? c.status}{c.approved_paise !== null ? ` · approved ${formatRupees(c.approved_paise)}` : ''}{c.policy_number ? ` · policy ${c.policy_number}` : ''}</Text>
            {open ? (
              <View style={{ gap: space.xs }}>
                <TextField label="Amount the insurer approved (₹)" keyboardType="decimal-pad" value={approved[c.id] ?? ''} onChangeText={(v) => setApproved((a) => ({ ...a, [c.id]: v }))} />
                <View style={{ flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' }}>
                  <Button size="sm" variant="secondary" title="Mark approved" disabled={amt === null} onPress={() => move.mutate({ id: c.id, status: amt === c.claimed_paise ? 'APPROVED' : 'PART_APPROVED', approved: amt as number })} />
                  {c.approved_paise !== null || amt !== null ? <Button size="sm" variant="secondary" title="Mark settled" onPress={() => move.mutate({ id: c.id, status: 'SETTLED', approved: amt ?? undefined })} /> : null}
                  <Button size="sm" variant="ghost" title="Rejected" onPress={() => move.mutate({ id: c.id, status: 'REJECTED' })} />
                </View>
              </View>
            ) : null}
          </View>
        );
      })}
      {adding ? (
        <View style={{ gap: space.sm }}>
          <TextField label="Insurer or TPA" value={insurer} onChangeText={setInsurer} />
          <TextField label="Policy number (optional)" value={policy} onChangeText={setPolicy} />
          <TextField label="Amount claimed (₹)" keyboardType="decimal-pad" value={amount} onChangeText={setAmount} />
          <Button title="Save claim" loading={create.isPending} disabled={insurer.trim().length < 2 || paise === null || paise <= 0} onPress={() => create.mutate()} />
          <Button title="Cancel" variant="ghost" onPress={() => setAdding(false)} />
        </View>
      ) : (
        <Button title="Add a claim" variant="secondary" onPress={() => setAdding(true)} />
      )}
    </Card>
  );
}

function IssuedView({ inv, canWrite, onChanged }: { inv: Invoice; canWrite: boolean; onChanged: () => void }) {
  const t = useTheme();
  const { me } = useAuth();
  const canAdjust = can(me, 'billing:adjust');
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
            <Text style={[type.body, { color: t.text, flex: 1 }]}>{l.description}{l.quantity > 1 ? ` × ${l.quantity}` : ''}{l.tax_rate_bp > 0 ? ` · tax ${percentLabel(l.tax_rate_bp)}` : ''}</Text>
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
          <ChoiceChips value={method} onChange={setMethod} options={(['CASH', 'UPI', 'CARD', 'INSURER', 'OTHER'] as const).map((m) => ({ value: m, label: METHOD_LABELS[m] }))} />
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
      {canWrite && inv.paid_paise === 0 && inv.credit_notes.length === 0 ? (
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
      {inv.credit_notes.length > 0 || inv.refunds.length > 0 ? (
        <Card title="Adjustments">
          {inv.credit_notes.map((c) => <Text key={c.number} style={[type.small, { color: t.text }]}>{c.number} · -{formatRupees(c.amount_paise)} · {c.reason}</Text>)}
          {inv.refunds.map((r, i) => <Text key={i} style={[type.small, { color: t.text }]}>Refunded {formatRupees(r.amount_paise)} · {METHOD_LABELS[r.method] ?? r.method} · {r.reason}</Text>)}
        </Card>
      ) : null}
      {canAdjust ? <Adjustments inv={inv} onChanged={onChanged} /> : null}
      {canAdjust ? <Claims inv={inv} /> : null}
      {canWrite && (inv.paid_paise > 0 || inv.credit_notes.length > 0) ? <Text style={[type.caption, { color: t.textMuted }]}>Money or a credit note is recorded, so this invoice cannot be voided. To cancel it, issue a credit note for the full amount and refund what was paid.</Text> : null}
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
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md, width: '100%', maxWidth: 720 }} keyboardShouldPersistTaps="handled">
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

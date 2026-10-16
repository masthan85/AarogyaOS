import { useState } from 'react';
import { Alert, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import { createPrescription, signPrescription, updatePrescription, voidPrescription, type RxItemInput } from '@/api/endpoints';
import { type Prescription, type SafetyWarning, safetyWarningSchema } from '@/api/schemas';
import { AlertBanner, Button, Card, ChoiceChips, SectionTitle, StatusChip, TextField } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
import { itemsFromPrescription, parseNumber } from '@/domain/clinical';
import { prescriptionHtml, type Letterhead } from '@/domain/print';
import { printHtml, sharePdf } from '@/services/print';

import { useAction } from './useAction';
import type { EncounterData } from './useEncounterData';

const ROUTES = ['ORAL', 'IV', 'IM', 'SC', 'TOPICAL', 'INHALED', 'SUBLINGUAL', 'OTHER'] as const;
const BLANK = { medicine_name: '', strength: '', dose: '', route: 'ORAL', frequency: '', days: '', instructions: '' };

export function PrescriptionPanel({ encId, data, letterhead }: { encId: string; data: EncounterData; letterhead: Letterhead | null }) {
  const t = useTheme();
  const [f, setF] = useState(BLANK);
  const [items, setItems] = useState<RxItemInput[]>([]);
  // Warnings the server returned when signing; each must be acknowledged explicitly.
  // The draft being corrected, if any; saving then replaces its lines instead of writing a new prescription.
  const [editing, setEditing] = useState<string | null>(null);
  const [pending, setPending] = useState<{ rxId: string; warnings: SafetyWarning[] } | null>(null);
  const done = () => void data.refresh();

  const addItem = () => {
    const days = parseNumber(f.days);
    if (Number.isNaN(days)) return Alert.alert('Check the number of days', 'Use digits only.');
    setItems((p) => [...p, {
      medicine_name: f.medicine_name.trim(), strength: f.strength.trim() || undefined, dose: f.dose.trim(),
      route: f.route, frequency: f.frequency.trim(), duration_days: days, instructions: f.instructions.trim() || undefined,
    }]);
    setF(BLANK);
  };
  const save = useAction(
    () => (editing ? updatePrescription(editing, items) : createPrescription(encId, items)),
    () => { setItems([]); setEditing(null); done(); },
  );
  const share = useAction(async (html: string) => sharePdf(html, 'Prescription'));
  const print = useAction(async (html: string) => printHtml(html));
  const void_ = useAction((id: string) => voidPrescription(id, 'Voided by doctor'), done);

  const sign = useAction(async (rx: Prescription, acknowledged: string[]) => {
    try {
      const signed = await signPrescription(rx.id, acknowledged);
      setPending(null);
      return signed;
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && Array.isArray(e.body?.warnings)) {
        setPending({ rxId: rx.id, warnings: e.body.warnings.map((w) => safetyWarningSchema.parse(w)) });
        return undefined;
      }
      throw e;
    }
  }, done);

  const prescriptions = data.detail?.prescriptions ?? [];
  const valid = f.medicine_name.trim().length >= 2 && f.dose.trim() && f.frequency.trim();

  return (
    <View style={{ gap: space.md }}>
      <SectionTitle>Prescriptions</SectionTitle>
      {prescriptions.length === 0 ? <Card><Text style={{ color: t.textMuted }}>None written.</Text></Card> : null}
      {prescriptions.map((rx) => (
        <Card key={rx.id}>
          <StatusChip label={rx.status === 'SIGNED' ? 'Signed' : rx.status === 'VOIDED' ? 'Voided' : 'Draft — not yet issued'}
            tone={rx.status === 'SIGNED' ? 'success' : rx.status === 'VOIDED' ? 'danger' : 'warning'} />
          {rx.items.map((i) => (
            <Text key={i.id} style={{ color: t.text }}>
              {i.position}. {i.medicine_name}{i.strength ? ` ${i.strength}` : ''} — {i.dose}, {i.route.toLowerCase()}, {i.frequency}{i.duration_days ? ` for ${i.duration_days} days` : ''}
            </Text>
          ))}
          {pending?.rxId === rx.id ? (
            <View style={{ gap: space.sm }}>
              <Text style={{ color: t.text, fontWeight: '700' }}>Check before signing</Text>
              {pending.warnings.map((w) => <AlertBanner key={w.code} level="WARNING" message={w.message} />)}
              <Button title="I have reviewed these — sign" variant="danger" loading={sign.pending}
                onPress={() => void sign.run(rx, pending.warnings.map((w) => w.code))} />
            </View>
          ) : null}
          {rx.status === 'DRAFT' && pending?.rxId !== rx.id ? (
            <Button title="Review and sign" loading={sign.pending} onPress={() => void sign.run(rx, [])} />
          ) : null}
          {rx.status === 'SIGNED' && letterhead ? (
            <View style={{ flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' }}>
              <Button title="Share as PDF" variant="secondary" loading={share.pending}
                onPress={() => { const h = prescriptionHtml(rx, letterhead); if (h) void share.run(h); }} />
              <Button title="Print" variant="secondary" loading={print.pending}
                onPress={() => { const h = prescriptionHtml(rx, letterhead); if (h) void print.run(h); }} />
            </View>
          ) : null}
          {rx.status === 'DRAFT' ? (
            <Button title="Edit draft" variant="secondary" onPress={() => { setItems(itemsFromPrescription(rx)); setEditing(rx.id); setPending(null); }} />
          ) : null}
          {rx.status !== 'VOIDED' ? (
            <Button title={rx.status === 'SIGNED' ? 'Void prescription' : 'Discard draft'} variant="secondary"
              onPress={() => Alert.alert(rx.status === 'SIGNED' ? 'Void this prescription?' : 'Discard this draft?', 'This cannot be undone.', [
                { text: 'Keep', style: 'cancel' }, { text: 'Yes', style: 'destructive', onPress: () => void void_.run(rx.id) },
              ])} />
          ) : null}
        </Card>
      ))}

      <Card title={editing ? 'Edit draft prescription' : 'Write a prescription'}>
        {items.map((i, n) => (
          <View key={n} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: space.sm }}>
            <Text style={{ color: t.text, flex: 1 }}>{n + 1}. {i.medicine_name}{i.strength ? ` ${i.strength}` : ''} — {i.dose}, {i.route.toLowerCase()}, {i.frequency}{i.duration_days ? ` for ${i.duration_days} days` : ''}</Text>
            <Button title="Remove" variant="secondary" onPress={() => setItems((p) => p.filter((_, k) => k !== n))} />
          </View>
        ))}
        <TextField label="Medicine" value={f.medicine_name} onChangeText={(v) => setF({ ...f, medicine_name: v })} />
        <View style={{ flexDirection: 'row', gap: space.md }}>
          <View style={{ flex: 1 }}><TextField label="Strength" placeholder="500 mg" value={f.strength} onChangeText={(v) => setF({ ...f, strength: v })} /></View>
          <View style={{ flex: 1 }}><TextField label="Dose" placeholder="1 tablet" value={f.dose} onChangeText={(v) => setF({ ...f, dose: v })} /></View>
        </View>
        <ChoiceChips label="Route" value={f.route} onChange={(v) => setF({ ...f, route: v })} options={ROUTES.map((r) => ({ value: r, label: r.toLowerCase() }))} />
        <View style={{ flexDirection: 'row', gap: space.md }}>
          <View style={{ flex: 2 }}><TextField label="How often" placeholder="twice daily" value={f.frequency} onChangeText={(v) => setF({ ...f, frequency: v })} /></View>
          <View style={{ flex: 1 }}><TextField label="Days" keyboardType="number-pad" value={f.days} onChangeText={(v) => setF({ ...f, days: v })} /></View>
        </View>
        <TextField label="Instructions" value={f.instructions} onChangeText={(v) => setF({ ...f, instructions: v })} />
        <Button title="Add medicine to prescription" variant="secondary" disabled={!valid} onPress={addItem} />
        {editing ? <Button title="Stop editing" variant="secondary" onPress={() => { setEditing(null); setItems([]); }} /> : null}
        <Button title={editing ? `Save changes (${items.length})` : `Save draft (${items.length})`} disabled={items.length === 0} loading={save.pending} onPress={() => void save.run()} />
        <Text style={{ color: t.textMuted, fontSize: 12 }}>
          Only you can sign. Safety checks cover allergy name matches and duplicates only — interactions, contraindications and doses are not checked.
        </Text>
      </Card>
    </View>
  );
}

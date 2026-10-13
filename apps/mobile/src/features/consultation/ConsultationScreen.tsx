import { useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { ScrollView, Text, useWindowDimensions, View } from 'react-native';

import { Card, ChoiceChips, ErrorState, LoadingState, StatusChip } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';

import { ContextPanel } from './ContextPanel';
import { DiagnosisPanel } from './DiagnosisPanel';
import { FinishPanel } from './FinishPanel';
import { FollowUpPanel } from './FollowUpPanel';
import { NotesPanel } from './NotesPanel';
import { OrdersPanel } from './OrdersPanel';
import { PrescriptionPanel } from './PrescriptionPanel';
import { useEncounterData } from './useEncounterData';

type Tab = 'context' | 'notes' | 'diagnosis' | 'orders' | 'prescription' | 'followup' | 'finish';
const TABS: { value: Tab; label: string }[] = [
  { value: 'context', label: 'Patient' },
  { value: 'notes', label: 'Notes' },
  { value: 'diagnosis', label: 'Diagnosis' },
  { value: 'orders', label: 'Tests' },
  { value: 'prescription', label: 'Prescription' },
  { value: 'followup', label: 'Follow-up' },
  { value: 'finish', label: 'Finish' },
];

export function ConsultationScreen() {
  const t = useTheme();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { width } = useWindowDimensions();
  // Tablet landscape: patient context stays beside the work. Phones get it as the first tab.
  const wide = width >= 900;
  const data = useEncounterData(id);
  const [tab, setTab] = useState<Tab>(wide ? 'notes' : 'context');

  if (data.isPending) return <LoadingState label="Opening consultation…" />;
  if (data.isError || !data.detail) return <ErrorState message="Could not open this visit." onRetry={() => data.retry()} />;
  const closed = data.detail.encounter.status === 'COMPLETED';
  const p = data.patient;

  const panel = (
    <>
      {tab === 'context' ? <ContextPanel data={data} /> : null}
      {tab === 'notes' ? <NotesPanel encId={id} data={data} /> : null}
      {tab === 'diagnosis' ? <DiagnosisPanel encId={id} data={data} /> : null}
      {tab === 'orders' ? <OrdersPanel encId={id} data={data} /> : null}
      {tab === 'prescription' ? <PrescriptionPanel encId={id} data={data} /> : null}
      {tab === 'followup' ? <FollowUpPanel encId={id} data={data} /> : null}
      {tab === 'finish' ? <FinishPanel encId={id} data={data} /> : null}
    </>
  );

  return (
    <View style={{ flex: 1 }}>
      {/* Patient header: identity and visit state are always on screen. */}
      <View style={{ padding: space.md, paddingBottom: 0 }}>
        <Card>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: space.sm }}>
            <View>
              <Text style={{ color: t.text, fontSize: 20, fontWeight: '800' }}>{p?.full_name ?? 'Patient'}</Text>
              <Text style={{ color: t.textMuted }}>{p ? `${p.mrn} · ${p.age_years ?? '?'} yrs · ${p.administrative_gender}` : ''}</Text>
            </View>
            <View style={{ flexDirection: 'row', gap: space.sm }}>
              {data.detail.encounter.triage_category ? <StatusChip label={data.detail.encounter.triage_category.toLowerCase()} tone={data.detail.encounter.triage_category === 'ROUTINE' ? 'neutral' : 'danger'} /> : null}
              <StatusChip label={closed ? 'Completed' : 'In consultation'} tone={closed ? 'neutral' : 'success'} />
            </View>
          </View>
        </Card>
      </View>
      <View style={{ padding: space.md }}>
        <ChoiceChips value={tab} onChange={setTab} options={wide ? TABS.filter((x) => x.value !== 'context') : TABS} />
      </View>
      {wide ? (
        <View style={{ flex: 1, flexDirection: 'row' }}>
          <ScrollView style={{ flex: 2 }} contentContainerStyle={{ padding: space.md, paddingTop: 0 }}>{panel}</ScrollView>
          <ScrollView style={{ flex: 1.3 }} contentContainerStyle={{ padding: space.md, paddingTop: 0 }}>
            <ContextPanel data={data} />
          </ScrollView>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: space.md, paddingTop: 0 }} keyboardShouldPersistTaps="handled">{panel}</ScrollView>
      )}
    </View>
  );
}

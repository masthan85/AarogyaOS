import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ScrollView, Text, useWindowDimensions, View } from 'react-native';

import { analyseInteraction, getPatientInteractions } from '@/api/endpoints';
import { useAuth } from '@/auth/AuthProvider';
import { Card, ChoiceChips, ErrorState, LoadingState, StatusChip } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
import { can } from '@/domain/permissions';
import { ConversationPanel } from '@/features/recording/ConversationPanel';
import { RecordingBar } from '@/features/recording/RecordingBar';
import { useRecordingSession } from '@/features/recording/useRecordingSession';

import { AssistPanel } from './AssistPanel';
import { DocumentsPanel } from './DocumentsPanel';
import { ContextPanel } from './ContextPanel';
import { DiagnosisPanel } from './DiagnosisPanel';
import { FinishPanel } from './FinishPanel';
import { FollowUpPanel } from './FollowUpPanel';
import { NotesPanel } from './NotesPanel';
import { OrdersPanel } from './OrdersPanel';
import { PrescriptionPanel } from './PrescriptionPanel';
import { type EncounterData, useEncounterData } from './useEncounterData';

type Tab = 'context' | 'conversation' | 'assist' | 'notes' | 'diagnosis' | 'orders' | 'prescription' | 'followup' | 'documents' | 'finish';
const TABS: { value: Tab; label: string }[] = [
  { value: 'context', label: 'Patient' },
  { value: 'conversation', label: 'Conversation' },
  { value: 'assist', label: 'Assist' },
  { value: 'notes', label: 'Notes' },
  { value: 'diagnosis', label: 'Diagnosis' },
  { value: 'orders', label: 'Tests' },
  { value: 'prescription', label: 'Prescription' },
  { value: 'followup', label: 'Follow-up' },
  { value: 'documents', label: 'Documents' },
  { value: 'finish', label: 'Finish' },
];

export function ConsultationScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const data = useEncounterData(id);
  if (data.isPending) return <LoadingState label="Opening consultation…" />;
  if (data.isError || !data.detail) return <ErrorState message="Could not open this visit." onRetry={() => data.retry()} />;
  return <ConsultationBody id={id} data={data} patientId={data.detail.encounter.patient_id} />;
}

function ConsultationBody({ id, data, patientId }: { id: string; data: EncounterData; patientId: string }) {
  const t = useTheme();
  const { me } = useAuth();
  const { width } = useWindowDimensions();
  // Tablet landscape: patient context stays beside the work. Phones get it as the first tab.
  const wide = width >= 900;
  const canRecord = can(me, 'interaction:consultation');
  const [ai, setAi] = useState(false);
  const rec = useRecordingSession({ patientId, encounterId: id, languageHint: data.patient?.preferred_language, ai });
  const canAssist = can(me, 'ai:review');
  const tabs = TABS.filter((x) => (x.value !== 'conversation' || canRecord) && (x.value !== 'assist' || canAssist) && (x.value !== 'documents' || can(me, 'summary:write')) && !(wide && x.value === 'context'));
  const [tab, setTab] = useState<Tab>(wide ? 'notes' : 'context');
  const closed = data.detail?.encounter.status === 'COMPLETED';

  // If the app was reopened mid-consultation, pick up the recording that is still open.
  const existing = useQuery({ queryKey: ['patient-interactions', patientId], queryFn: () => getPatientInteractions(patientId), enabled: canRecord, gcTime: 0 });
  useEffect(() => {
    const open = existing.data?.find((i) => i.encounter_id === id && i.status !== 'ENDED');
    if (open && rec.phase === 'idle') void rec.adopt(open);
  }, [existing.data, id, rec]);

  // While a consented AI recording is live, look for new candidates every 30 seconds. This is a
  // convenience only: failures are ignored, nothing waits on it, and manual analysis is always there.
  const qc = useQueryClient();
  const liveId = rec.phase === 'live' && ai ? rec.interaction?.id : undefined;
  useEffect(() => {
    if (!liveId) return;
    const timer = setInterval(() => {
      analyseInteraction(liveId)
        .then(() => qc.invalidateQueries({ queryKey: ['ai-review', id] }))
        .catch(() => undefined);
    }, 30000);
    return () => clearInterval(timer);
  }, [liveId, id, qc]);

  const detail = data.detail;
  if (!detail) return null;
  const p = data.patient;

  const panel = (
    <>
      {tab === 'context' ? <ContextPanel data={data} /> : null}
      {tab === 'conversation' ? <ConversationPanel rec={rec} patientId={patientId} closed={!!closed} ai={ai} onAiChange={setAi} /> : null}
      {tab === 'assist' ? <AssistPanel encId={id} data={data} rec={rec} isDoctor={can(me, 'note:clinical')} /> : null}
      {tab === 'notes' ? <NotesPanel encId={id} data={data} /> : null}
      {tab === 'diagnosis' ? <DiagnosisPanel encId={id} data={data} /> : null}
      {tab === 'orders' ? <OrdersPanel encId={id} data={data} /> : null}
      {tab === 'prescription' ? <PrescriptionPanel encId={id} data={data} /> : null}
      {tab === 'followup' ? <FollowUpPanel encId={id} data={data} /> : null}
      {tab === 'documents' ? <DocumentsPanel encId={id} patientLanguage={data.patient?.preferred_language} /> : null}
      {tab === 'finish' ? <FinishPanel encId={id} data={data} /> : null}
    </>
  );

  return (
    <View style={{ flex: 1 }}>
      {/* Patient header: identity and visit state are always on screen. */}
      <View style={{ padding: space.md, paddingBottom: 0, gap: space.sm }}>
        <Card>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: space.sm }}>
            <View>
              <Text style={{ color: t.text, fontSize: 20, fontWeight: '800' }}>{p?.full_name ?? 'Patient'}</Text>
              <Text style={{ color: t.textMuted }}>{p ? `${p.mrn} · ${p.age_years ?? '?'} yrs · ${p.administrative_gender}` : ''}</Text>
            </View>
            <View style={{ flexDirection: 'row', gap: space.sm }}>
              {detail.encounter.triage_category ? <StatusChip label={detail.encounter.triage_category.toLowerCase()} tone={detail.encounter.triage_category === 'ROUTINE' ? 'neutral' : 'danger'} /> : null}
              <StatusChip label={closed ? 'Completed' : 'In consultation'} tone={closed ? 'neutral' : 'success'} />
            </View>
          </View>
        </Card>
        {/* Visible on every tab while a recording exists: the state must never be out of sight. */}
        <RecordingBar rec={rec} />
      </View>
      <View style={{ padding: space.md }}>
        <ChoiceChips value={tab} onChange={setTab} options={tabs} />
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

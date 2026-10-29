import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';

import { captureConsent, type ConsentInput, getConsentPolicies, getPatient, getPatientConsents, withdrawConsent } from '@/api/endpoints';
import type { PurposeStatus } from '@/api/schemas';
import { useAuth } from '@/auth/AuthProvider';
import { AlertBanner, Button, Card, ChoiceChips, ErrorState, LoadingState, SectionTitle, StatusChip, TextField } from '@/design-system/components';
import { space, useTheme, type } from '@/design-system/tokens';
import { can } from '@/domain/permissions';
import { CONSENT_GROUPS, PURPOSE_LABELS } from '@/domain/recording';
import { useAction } from '@/features/consultation/useAction';

type Method = ConsentInput['method'];

export function ConsentScreen() {
  const t = useTheme();
  const qc = useQueryClient();
  const { me } = useAuth();
  const { patientId } = useLocalSearchParams<{ patientId: string }>();
  const patient = useQuery({ queryKey: ['patient', patientId], queryFn: () => getPatient(patientId), gcTime: 0 });
  const consents = useQuery({ queryKey: ['patient-consents', patientId], queryFn: () => getPatientConsents(patientId), gcTime: 0 });
  const policies = useQuery({ queryKey: ['consent-policies'], queryFn: getConsentPolicies });
  const [method, setMethod] = useState<Method>('VERBAL_WITNESSED');
  const [proxy, setProxy] = useState(false);
  const [name, setName] = useState('');
  const [relation, setRelation] = useState('');
  const [open, setOpen] = useState<string | null>(null);

  const refresh = () => void qc.invalidateQueries({ queryKey: ['patient-consents', patientId] });
  const grant = useAction((purpose: string, byRep: boolean) =>
    captureConsent(patientId, {
      purpose, method,
      granted_by_type: byRep ? 'REPRESENTATIVE' : 'PATIENT',
      ...(byRep ? { representative_name: name.trim(), representative_relationship: relation.trim() } : {}),
    }), refresh);
  const withdraw = useAction((id: string) => withdrawConsent(id, 'Withdrawn at the patient’s request'), refresh);

  if (consents.isPending || patient.isPending) return <LoadingState label="Loading consent…" />;
  if (consents.isError || !consents.data) return <ErrorState message="Could not load consent." onRetry={() => consents.refetch()} />;
  const data = consents.data;
  const byPurpose = new Map<string, PurposeStatus>(data.status.map((s) => [s.purpose, s]));
  const mustUseGuardian = data.guardian_required;
  const byRep = mustUseGuardian || proxy;
  const repReady = !byRep || (name.trim().length > 1 && relation.trim().length > 1);
  const canCapture = can(me, 'consent:capture');
  const wording = (purpose: string) => policies.data?.find((p) => p.purpose === purpose && p.language === (patient.data?.preferred_language ?? 'en-IN'))
    ?? policies.data?.find((p) => p.purpose === purpose && p.language === 'en-IN');

  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md }} keyboardShouldPersistTaps="handled">
      <Card>
        <Text style={[type.title, { color: t.text }]}>{patient.data?.full_name ?? 'Patient'}</Text>
        <Text style={{ color: t.textMuted }}>
          Read each item to the patient in their language ({patient.data?.preferred_language}). Each one is a separate decision.
        </Text>
      </Card>

      {mustUseGuardian ? <AlertBanner level="WARNING" message="This patient is a minor. A parent or guardian must give consent." /> : null}
      {canCapture ? (
        <Card title="Who is giving consent?">
          {!mustUseGuardian ? (
            <ChoiceChips value={proxy ? 'rep' : 'self'} onChange={(v) => setProxy(v === 'rep')} options={[{ value: 'self', label: 'The patient' }, { value: 'rep', label: 'A family member / guardian' }]} />
          ) : null}
          {byRep ? (
            <>
              <TextField label="Their name" value={name} onChangeText={setName} />
              <TextField label="Relationship to the patient" placeholder="e.g. Mother, Son" value={relation} onChangeText={setRelation} />
            </>
          ) : null}
          <ChoiceChips label="How was it given?" value={method} onChange={setMethod} options={[{ value: 'VERBAL_WITNESSED', label: 'Spoken' }, { value: 'ON_DEVICE', label: 'On this device' }, { value: 'PAPER', label: 'Paper form' }]} />
        </Card>
      ) : null}

      {CONSENT_GROUPS.map((g) => (
        <View key={g.title} style={{ gap: space.sm }}>
          <SectionTitle>{g.title}</SectionTitle>
          <Text style={{ color: t.textMuted }}>{g.hint}</Text>
          {g.purposes.map((purpose) => {
            const st = byPurpose.get(purpose);
            const w = wording(purpose);
            return (
              <Card key={purpose} title={PURPOSE_LABELS[purpose] ?? purpose}>
                <View style={{ flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' }}>
                  <StatusChip label={st?.active ? `Given${st.granted_by_type === 'REPRESENTATIVE' ? ' (by representative)' : ''}` : st?.blocked_by ? `Off: needs ${PURPOSE_LABELS[st.blocked_by]}` : 'Not given'} tone={st?.active ? 'success' : st?.blocked_by ? 'warning' : 'neutral'} />
                  {w && !w.legally_reviewed ? <StatusChip label="template wording" tone="warning" /> : null}
                </View>
                {w ? (
                  <>
                    <Text style={{ color: t.primary, fontWeight: '600' }} onPress={() => setOpen(open === purpose ? null : purpose)}>
                      {open === purpose ? 'Hide wording' : 'Show wording to read out'}
                    </Text>
                    {open === purpose ? <Text style={[type.body, { color: t.text }]}>{w.body}</Text> : null}
                  </>
                ) : <Text style={{ color: t.danger }}>No wording published yet. Ask an administrator.</Text>}
                {canCapture && !st?.active && w ? (
                  <Button title="Patient agrees" disabled={!repReady} loading={grant.pending} onPress={() => void grant.run(purpose, byRep)} />
                ) : null}
                {can(me, 'consent:withdraw') && st?.active && st.consent_id ? (
                  <Button title="Withdraw consent" variant="secondary"
                    onPress={() => Alert.alert('Withdraw this consent?', purpose === 'AUDIO_RECORDING' || purpose === 'SPEECH_TRANSCRIPTION' ? 'Any recording in progress will stop immediately.' : 'This takes effect immediately.', [
                      { text: 'Keep', style: 'cancel' },
                      { text: 'Withdraw', style: 'destructive', onPress: () => void withdraw.run(st.consent_id as string) },
                    ])} />
                ) : null}
              </Card>
            );
          })}
        </View>
      ))}
    </ScrollView>
  );
}

import { useMutation, useQuery } from '@tanstack/react-query';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';

import { getClinicalState, getHolds, getPatient, getTimeline, placeHold, releaseHold } from '@/api/endpoints';
import { useAuth } from '@/auth/AuthProvider';
import { AlertBanner, Button, Card, EmptyState, ErrorState, LoadingState, StatusChip, TextField } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
import { formatDateTime } from '@/domain/dates';
import { eventLabel } from '@/domain/events';
import { can } from '@/domain/permissions';

/** Admins only: stops retention jobs deleting anything about this patient while a legal matter is open. */
function LegalHold({ patientId }: { patientId: string }) {
  const t = useTheme();
  const holds = useQuery({ queryKey: ['legal-holds', patientId], queryFn: () => getHolds(patientId), gcTime: 0 });
  const [reason, setReason] = useState('');
  const refresh = () => { setReason(''); void holds.refetch(); };
  const fail = (e: unknown) => Alert.alert('Not saved', e instanceof Error ? e.message : 'Check your connection.');
  const place = useMutation({ mutationFn: () => placeHold(patientId, reason.trim()), onSuccess: refresh, onError: fail });
  const release = useMutation({ mutationFn: (id: string) => releaseHold(id, reason.trim()), onSuccess: refresh, onError: fail });
  const active = holds.data?.[0];
  return (
    <Card title="Legal hold">
      {active ? (
        <Text style={{ color: t.warning, fontWeight: '700' }}>On hold: {active.reason}. Deletion jobs will skip this patient, including audio whose time is up or whose consent was withdrawn.</Text>
      ) : (
        <Text style={{ color: t.textMuted }}>No hold. Place one when a complaint, claim or legal notice means records must be kept.</Text>
      )}
      <TextField label={active ? 'Why is the hold being released?' : 'Reason for the hold'} value={reason} onChangeText={setReason} />
      {active ? (
        <Button title="Release the hold" variant="secondary" disabled={reason.trim().length < 5} loading={release.isPending}
          onPress={() => Alert.alert('Release this hold?', 'Deletion jobs will treat this patient normally again.', [{ text: 'Keep it', style: 'cancel' }, { text: 'Release', onPress: () => release.mutate(active.id) }])} />
      ) : (
        <Button title="Place a legal hold" disabled={reason.trim().length < 5} loading={place.isPending} onPress={() => place.mutate()} />
      )}
    </Card>
  );
}

export function PatientProfileScreen() {
  const t = useTheme();
  const { me } = useAuth();
  const { id } = useLocalSearchParams<{ id: string }>();
  // Patient data is PHI: keep it in memory only while the screen is in use.
  const patient = useQuery({ queryKey: ['patient', id], queryFn: () => getPatient(id), gcTime: 0 });
  const showClinical = can(me, 'patient:clinical');
  const clinical = useQuery({ queryKey: ['clinical-state', id], queryFn: () => getClinicalState(id), enabled: showClinical, gcTime: 0 });
  const showTimeline = can(me, 'patient:timeline');
  const timeline = useQuery({
    queryKey: ['patient-timeline', id],
    queryFn: () => getTimeline(id),
    enabled: showTimeline,
    gcTime: 0,
  });

  if (patient.isPending) return <LoadingState label="Opening record…" />;
  if (patient.isError) return <ErrorState message="Could not open this patient." onRetry={() => patient.refetch()} />;
  const p = patient.data;

  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md }}>
      {/* Patient header: identity is always the first thing on screen. */}
      <Card>
        <Text style={{ color: t.text, fontSize: 24, fontWeight: '800' }}>{p.full_name}</Text>
        <Text style={{ color: t.textMuted }}>
          {p.mrn} · {p.age_years ?? '?'} yrs{p.dob_is_estimated ? ' (estimated)' : ''} · {p.administrative_gender}
        </Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
          <StatusChip label={`Language: ${p.preferred_language}`} />
          {p.identifiers.map((i) => (
            <StatusChip key={i.id} label={`${i.system.replace('_', ' ')} ${i.masked}${i.verified ? '' : ' (unverified)'}`} />
          ))}
        </View>
      </Card>

      {clinical.data?.alerts.map((a) => <AlertBanner key={a.code + a.message} level={a.level} message={a.message} />)}

      <Card title="Contact">
        <Text style={{ color: t.text }}>{p.mobile ?? 'No mobile number'}</Text>
        {p.address ? <Text style={{ color: t.textMuted }}>{p.address}</Text> : null}
        {p.emergency_contact_name ? (
          <Text style={{ color: t.textMuted }}>
            Emergency: {p.emergency_contact_name} {p.emergency_contact_phone ?? ''}
          </Text>
        ) : null}
      </Card>

      {can(me, 'appointment:manage') ? (
        <Button title="Book appointment" onPress={() => router.push({ pathname: '/appointments/book', params: { patientId: p.id, name: p.full_name } })} />
      ) : null}
      {can(me, 'consent:read') ? (
        <Button title="Consent" variant="secondary" onPress={() => router.push({ pathname: '/consent/[patientId]', params: { patientId: p.id } })} />
      ) : null}
      {can(me, 'queue:manage') ? (
        <Button title="Walk-in check-in" variant="secondary" onPress={() => router.push({ pathname: '/queue', params: { walkInPatientId: p.id, walkInName: p.full_name } })} />
      ) : null}

      {can(me, 'legalhold:manage') ? <LegalHold patientId={id} /> : null}

      {showTimeline ? (
        <Card title="Timeline">
          {timeline.isPending ? (
            <LoadingState />
          ) : timeline.isError ? (
            <ErrorState message="Could not load the timeline." onRetry={() => timeline.refetch()} />
          ) : timeline.data.length === 0 ? (
            <EmptyState message="Nothing recorded yet." />
          ) : (
            timeline.data.map((e) => (
              <View key={e.id} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: space.xs }}>
                <Text style={{ color: t.text }}>{eventLabel(e.event_type)}</Text>
                <Text style={{ color: t.textMuted }}>{formatDateTime(e.occurred_at)}</Text>
              </View>
            ))
          )}
        </Card>
      ) : null}
    </ScrollView>
  );
}

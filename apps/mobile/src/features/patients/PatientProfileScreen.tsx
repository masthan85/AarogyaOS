import { useQuery } from '@tanstack/react-query';
import { router, useLocalSearchParams } from 'expo-router';
import { ScrollView, Text, View } from 'react-native';

import { getPatient, getTimeline } from '@/api/endpoints';
import { useAuth } from '@/auth/AuthProvider';
import { Button, Card, EmptyState, ErrorState, LoadingState, StatusChip } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
import { formatDateTime } from '@/domain/dates';
import { eventLabel } from '@/domain/events';
import { can } from '@/domain/permissions';

export function PatientProfileScreen() {
  const t = useTheme();
  const { me } = useAuth();
  const { id } = useLocalSearchParams<{ id: string }>();
  // Patient data is PHI: keep it in memory only while the screen is in use.
  const patient = useQuery({ queryKey: ['patient', id], queryFn: () => getPatient(id), gcTime: 0 });
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
      {can(me, 'queue:manage') ? (
        <Button title="Walk-in check-in" variant="secondary" onPress={() => router.push({ pathname: '/queue', params: { walkInPatientId: p.id, walkInName: p.full_name } })} />
      ) : null}

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

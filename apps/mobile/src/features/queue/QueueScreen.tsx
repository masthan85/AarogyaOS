import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { router, useLocalSearchParams } from 'expo-router';
import { Alert, FlatList, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import { getQueue, startConsultation, walkIn } from '@/api/endpoints';
import type { QueueItem } from '@/api/schemas';
import { useAuth } from '@/auth/AuthProvider';
import { Button, Card, EmptyState, ErrorState, LoadingState, StatusChip } from '@/design-system/components';
import { space, useTheme, type } from '@/design-system/tokens';
import { formatTime } from '@/domain/dates';
import { can } from '@/domain/permissions';
import { useFacility } from '@/features/facility/useFacility';

export function QueueScreen() {
  const t = useTheme();
  const { me } = useAuth();
  const qc = useQueryClient();
  const { facilityId, picker } = useFacility();
  const { walkInPatientId, walkInName } = useLocalSearchParams<{ walkInPatientId?: string; walkInName?: string }>();
  const queue = useQuery({
    queryKey: ['queue', facilityId],
    queryFn: () => getQueue(facilityId as string),
    enabled: !!facilityId,
    refetchInterval: 15_000, // the waiting room changes constantly
  });
  const refresh = () => void qc.invalidateQueries({ queryKey: ['queue'] });
  const fail = (e: unknown) => Alert.alert('Could not complete', e instanceof ApiError ? e.message : 'Check your connection.');
  const consult = useMutation({
    mutationFn: (appointmentId: string) => startConsultation(appointmentId),
    onSuccess: (enc) => {
      refresh();
      router.push(`/consultation/${enc.id}`);
    },
    onError: fail,
  });
  const addWalkIn = useMutation({
    mutationFn: (priority: 'ROUTINE' | 'URGENT') =>
      walkIn({ patient_id: walkInPatientId as string, facility_id: facilityId as string, priority }),
    onSuccess: refresh,
    onError: fail,
  });
  const canTriage = can(me, 'encounter:triage');
  const canConsult = can(me, 'encounter:consult');

  const row = (q: QueueItem) => (
    <Card>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text style={[type.display, { color: t.primary }]}>{q.token_number}</Text>
        <View style={{ flexDirection: 'row', gap: space.sm }}>
          {q.priority === 'URGENT' ? <StatusChip label="Urgent" tone="danger" /> : null}
          <StatusChip label={q.status === 'IN_CONSULTATION' ? 'With doctor' : 'Waiting'} tone={q.status === 'IN_CONSULTATION' ? 'success' : 'warning'} />
        </View>
      </View>
      <Text style={[type.h3, { color: t.text }]}>{q.patient_name}</Text>
      <Text style={{ color: t.textMuted }}>
        {q.patient_mrn} · {q.age_years ?? '?'} yrs · since {formatTime(q.waiting_since)}
        {q.practitioner_name ? ` · ${q.practitioner_name}` : ''}
      </Text>
      {q.encounter_status === 'TRIAGE' || q.encounter_status === 'IN_PROGRESS' ? (
        <StatusChip label={q.encounter_status === 'TRIAGE' ? 'Triage started' : 'Consultation open'} tone="success" />
      ) : (
        <StatusChip label="Not triaged" />
      )}
      {canTriage && q.status !== 'IN_CONSULTATION' ? (
        <Button
          title={q.encounter_status ? 'Continue triage' : 'Start triage'}
          variant="secondary"
          onPress={() => router.push({ pathname: '/triage/[appointmentId]', params: { appointmentId: q.appointment_id, name: q.patient_name } })}
        />
      ) : null}
      {canConsult ? (
        <Button
          title={q.status === 'IN_CONSULTATION' ? 'Resume consultation' : 'Start consultation'}
          loading={consult.isPending && consult.variables === q.appointment_id}
          onPress={() => consult.mutate(q.appointment_id)}
        />
      ) : null}
    </Card>
  );

  return (
    <View style={{ flex: 1 }}>
      <View style={{ padding: space.md, gap: space.sm }}>
        {picker}
        {walkInPatientId && facilityId ? (
          <Card title={`Check in ${walkInName ?? 'patient'} as a walk-in`}>
            <Button title="Add to queue" onPress={() => addWalkIn.mutate('ROUTINE')} loading={addWalkIn.isPending} />
            <Button title="Add as urgent" variant="danger" onPress={() => addWalkIn.mutate('URGENT')} />
          </Card>
        ) : null}
      </View>
      {queue.isPending && facilityId ? <LoadingState /> : queue.isError ? (
        <ErrorState message="Could not load the queue." onRetry={() => queue.refetch()} />
      ) : (
        <FlatList
          data={queue.data ?? []}
          keyExtractor={(q) => q.appointment_id}
          contentContainerStyle={{ padding: space.md, gap: space.md }}
          refreshing={queue.isRefetching}
          onRefresh={() => queue.refetch()}
          ListEmptyComponent={<EmptyState message="Nobody is waiting." />}
          renderItem={({ item }) => row(item)}
        />
      )}
    </View>
  );
}

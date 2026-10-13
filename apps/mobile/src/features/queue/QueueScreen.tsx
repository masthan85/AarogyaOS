import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useLocalSearchParams } from 'expo-router';
import { Alert, FlatList, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import { completeConsultation, getQueue, startConsultation, walkIn } from '@/api/endpoints';
import type { QueueItem } from '@/api/schemas';
import { useAuth } from '@/auth/AuthProvider';
import { Button, Card, EmptyState, ErrorState, LoadingState, StatusChip } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
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
  const start = useMutation({ mutationFn: startConsultation, onSuccess: refresh, onError: fail });
  const finish = useMutation({ mutationFn: completeConsultation, onSuccess: refresh, onError: fail });
  const addWalkIn = useMutation({
    mutationFn: (priority: 'ROUTINE' | 'URGENT') =>
      walkIn({ patient_id: walkInPatientId as string, facility_id: facilityId as string, priority }),
    onSuccess: refresh,
    onError: fail,
  });
  const canCall = can(me, 'queue:call');

  const row = (q: QueueItem) => (
    <Card>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text style={{ color: t.primary, fontSize: 28, fontWeight: '800' }}>{q.token_number}</Text>
        <View style={{ flexDirection: 'row', gap: space.sm }}>
          {q.priority === 'URGENT' ? <StatusChip label="Urgent" tone="danger" /> : null}
          <StatusChip label={q.status === 'IN_CONSULTATION' ? 'With doctor' : 'Waiting'} tone={q.status === 'IN_CONSULTATION' ? 'success' : 'warning'} />
        </View>
      </View>
      <Text style={{ color: t.text, fontWeight: '700', fontSize: 17 }}>{q.patient_name}</Text>
      <Text style={{ color: t.textMuted }}>
        {q.patient_mrn} · {q.age_years ?? '?'} yrs · since {formatTime(q.waiting_since)}
        {q.practitioner_name ? ` · ${q.practitioner_name}` : ''}
      </Text>
      {canCall && q.status !== 'IN_CONSULTATION' ? <Button title="Call patient" onPress={() => start.mutate(q.appointment_id)} loading={start.isPending && start.variables === q.appointment_id} /> : null}
      {canCall && q.status === 'IN_CONSULTATION' ? <Button title="Complete visit" variant="secondary" onPress={() => finish.mutate(q.appointment_id)} /> : null}
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

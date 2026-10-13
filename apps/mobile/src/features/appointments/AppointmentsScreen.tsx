import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, FlatList, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import { cancelAppointment, checkIn, getAppointments } from '@/api/endpoints';
import type { Appointment } from '@/api/schemas';
import { useAuth } from '@/auth/AuthProvider';
import { Button, Card, EmptyState, ErrorState, LoadingState, StatusChip } from '@/design-system/components';
import type { ChipTone } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
import { addDays, formatDay, formatTime, toDateString } from '@/domain/dates';
import { can } from '@/domain/permissions';
import { useFacility } from '@/features/facility/useFacility';

const TONE: Record<string, ChipTone> = {
  BOOKED: 'neutral', CONFIRMED: 'neutral', WAITING: 'warning', IN_CONSULTATION: 'success',
  COMPLETED: 'success', CANCELLED: 'danger', NO_SHOW: 'danger',
};

export function AppointmentsScreen() {
  const t = useTheme();
  const { me } = useAuth();
  const qc = useQueryClient();
  const { facilityId, picker } = useFacility();
  const [offset, setOffset] = useState(0);
  const day = addDays(new Date(), offset);
  const list = useQuery({
    queryKey: ['appointments', facilityId, toDateString(day)],
    queryFn: () => getAppointments({ on: toDateString(day), facility_id: facilityId }),
    enabled: !!facilityId,
  });
  const refresh = () => void qc.invalidateQueries({ queryKey: ['appointments'] });
  const fail = (e: unknown) => Alert.alert('Could not complete', e instanceof ApiError ? e.message : 'Check your connection.');
  const checkInM = useMutation({ mutationFn: (id: string) => checkIn(id), onSuccess: () => { refresh(); void qc.invalidateQueries({ queryKey: ['queue'] }); }, onError: fail });
  const cancelM = useMutation({ mutationFn: (id: string) => cancelAppointment(id), onSuccess: refresh, onError: fail });
  const manage = can(me, 'appointment:manage');
  const queueManage = can(me, 'queue:manage');
  const isToday = offset === 0;

  const row = (a: Appointment) => {
    const open = ['BOOKED', 'CONFIRMED'].includes(a.status);
    return (
      <Card>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text style={{ color: t.text, fontSize: 17, fontWeight: '700' }}>{formatTime(a.start_at)}</Text>
          <StatusChip label={a.status.replace('_', ' ')} tone={TONE[a.status] ?? 'neutral'} />
        </View>
        <Text style={{ color: t.text }}>{a.patient_name} · {a.patient_mrn}</Text>
        <Text style={{ color: t.textMuted }}>
          {a.practitioner_name ?? 'Any doctor'}{a.token_number ? ` · Token ${a.token_number}` : ''}
        </Text>
        <View style={{ gap: space.sm }}>
          {queueManage && isToday && open ? <Button title="Check in" onPress={() => checkInM.mutate(a.id)} loading={checkInM.isPending && checkInM.variables === a.id} /> : null}
          {manage && (open || a.status === 'WAITING') ? (
            <Button title="Cancel appointment" variant="secondary"
              onPress={() => Alert.alert('Cancel appointment?', `${a.patient_name} at ${formatTime(a.start_at)}`, [
                { text: 'Keep', style: 'cancel' },
                { text: 'Cancel appointment', style: 'destructive', onPress: () => cancelM.mutate(a.id) },
              ])} />
          ) : null}
        </View>
      </Card>
    );
  };

  return (
    <View style={{ flex: 1 }}>
      <View style={{ padding: space.md, gap: space.sm }}>
        {picker}
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <Button title="‹" variant="secondary" onPress={() => setOffset((o) => o - 1)} />
          <Text style={{ color: t.text, fontWeight: '700', fontSize: 17 }}>{isToday ? 'Today' : formatDay(day)}</Text>
          <Button title="›" variant="secondary" onPress={() => setOffset((o) => o + 1)} />
        </View>
        {can(me, 'patient:search') && manage ? (
          <Button title="Book for a patient" variant="secondary" onPress={() => router.push('/patients')} />
        ) : null}
      </View>
      {list.isPending && facilityId ? <LoadingState /> : list.isError ? (
        <ErrorState message="Could not load appointments." onRetry={() => list.refetch()} />
      ) : (
        <FlatList
          data={list.data ?? []}
          keyExtractor={(a) => a.id}
          contentContainerStyle={{ padding: space.md, gap: space.md }}
          refreshing={list.isRefetching}
          onRefresh={() => list.refetch()}
          ListEmptyComponent={<EmptyState message="No appointments on this day." />}
          renderItem={({ item }) => row(item)}
        />
      )}
    </View>
  );
}

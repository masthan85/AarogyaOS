import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, FlatList, Pressable, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import { cancelAppointment, checkIn, getAppointments } from '@/api/endpoints';
import type { Appointment } from '@/api/schemas';
import { useAuth } from '@/auth/AuthProvider';
import { Button, Card, EmptyState, ErrorState, LoadingState, StatusChip } from '@/design-system/components';
import type { ChipTone } from '@/design-system/components';
import { Icon, type IconName } from '@/design-system/icons';
import { MIN_TOUCH_SMALL, radius, space, useTheme, useWide, type } from '@/design-system/tokens';
import { addDays, formatDay, formatTime, toDateString } from '@/domain/dates';
import { can } from '@/domain/permissions';
import { sentence } from '@/domain/text';
import { useFacility } from '@/features/facility/useFacility';

const TONE: Record<string, ChipTone> = {
  BOOKED: 'neutral', CONFIRMED: 'neutral', WAITING: 'warning', IN_CONSULTATION: 'success',
  COMPLETED: 'success', CANCELLED: 'danger', NO_SHOW: 'danger',
};

export function AppointmentsScreen() {
  const t = useTheme();
  const wide = useWide();
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

  const step = (icon: IconName, label: string, by: number) => (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={() => setOffset((o) => o + by)}
      style={({ pressed }) => ({ width: MIN_TOUCH_SMALL, height: MIN_TOUCH_SMALL, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center', backgroundColor: t.primarySoft, opacity: pressed ? 0.7 : 1 })}>
      <Icon name={icon} size={20} color={t.primary} />
    </Pressable>
  );

  const row = (a: Appointment) => {
    const open = ['BOOKED', 'CONFIRMED'].includes(a.status);
    return (
      <Card>
        <View style={{ flexDirection: wide ? 'row' : 'column', alignItems: wide ? 'center' : 'stretch', gap: wide ? space.md : space.sm }}>
        <Text style={[type.title, { color: t.primary, minWidth: 96 }]}>{formatTime(a.start_at)}</Text>
        <View style={{ flex: 1, gap: 2 }}>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: space.sm }}>
            <Text style={[type.h3, { color: t.text }]}>{a.patient_name}</Text>
            <StatusChip label={sentence(a.status)} tone={TONE[a.status] ?? 'neutral'} />
          </View>
          <Text style={[type.small, { color: t.textMuted }]}>
            {a.patient_mrn} · {a.practitioner_name ?? 'Any doctor'}{a.token_number ? ` · Token ${a.token_number}` : ''}
          </Text>
        </View>
        <View style={{ gap: space.sm, flexDirection: wide ? 'row' : 'column' }}>
          {queueManage && isToday && open ? <Button title="Check in" onPress={() => checkInM.mutate(a.id)} loading={checkInM.isPending && checkInM.variables === a.id} /> : null}
          {manage && (open || a.status === 'WAITING') ? (
            <Button title="Cancel appointment" variant="secondary"
              onPress={() => Alert.alert('Cancel appointment?', `${a.patient_name} at ${formatTime(a.start_at)}`, [
                { text: 'Keep', style: 'cancel' },
                { text: 'Cancel appointment', style: 'destructive', onPress: () => cancelM.mutate(a.id) },
              ])} />
          ) : null}
        </View>
        </View>
      </Card>
    );
  };

  return (
    <View style={{ flex: 1 }}>
      <View style={{ padding: space.md, paddingBottom: 0, gap: space.sm }}>
        {picker}
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: wide ? 'flex-start' : 'space-between', gap: space.md }}>
          {step('chevron-left', 'Previous day', -1)}
          <Text style={[type.title, { color: t.text, minWidth: wide ? 160 : 0, textAlign: 'center' }]}>{isToday ? 'Today' : formatDay(day)}</Text>
          {step('chevron-right', 'Next day', 1)}
          {!isToday && wide ? <Button title="Back to today" variant="ghost" onPress={() => setOffset(0)} /> : null}
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

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import { bookAppointment, getPractitioners, getSlots } from '@/api/endpoints';
import { Button, Card, ChoiceChips, EmptyState, ErrorState, LoadingState } from '@/design-system/components';
import { MIN_TOUCH, space, useTheme } from '@/design-system/tokens';
import { addDays, formatDay, formatTime, toDateString } from '@/domain/dates';

export function BookAppointmentScreen() {
  const t = useTheme();
  const qc = useQueryClient();
  const { patientId, name } = useLocalSearchParams<{ patientId: string; name?: string }>();
  const [practitionerId, setPractitionerId] = useState<string>();
  const [dayOffset, setDayOffset] = useState(0);
  const [slot, setSlot] = useState<string>();
  const [error, setError] = useState<string>();

  const doctors = useQuery({ queryKey: ['practitioners'], queryFn: () => getPractitioners() });
  const day = addDays(new Date(), dayOffset);
  const slots = useQuery({
    queryKey: ['slots', practitionerId, toDateString(day)],
    queryFn: () => getSlots(practitionerId as string, toDateString(day)),
    enabled: !!practitionerId,
  });

  const book = useMutation({
    mutationFn: () => bookAppointment({ patient_id: patientId, practitioner_id: practitionerId as string, start_at: slot as string }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['appointments'] });
      router.back();
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : 'Could not book. Check your connection.');
      setSlot(undefined);
      void slots.refetch(); // someone else may have taken it: show the fresh list
    },
  });

  if (doctors.isPending) return <LoadingState label="Loading doctors…" />;
  if (doctors.isError) return <ErrorState message="Could not load doctors." onRetry={() => doctors.refetch()} />;

  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md }}>
      <Card title={`Book for ${name ?? 'patient'}`} />
      {doctors.data.length === 0 ? (
        <EmptyState message="No doctors are set up for booking yet. Ask an administrator to add practitioners." />
      ) : (
        <ChoiceChips
          label="Doctor"
          value={practitionerId}
          onChange={(v) => { setPractitionerId(v); setSlot(undefined); }}
          options={doctors.data.map((d) => ({ value: d.id, label: `${d.full_name} · ${d.specialty}` }))}
        />
      )}
      <ChoiceChips
        label="Day"
        value={String(dayOffset)}
        onChange={(v) => { setDayOffset(Number(v)); setSlot(undefined); }}
        options={[0, 1, 2, 3, 4, 5, 6].map((n) => ({ value: String(n), label: n === 0 ? 'Today' : formatDay(addDays(new Date(), n)) }))}
      />
      {practitionerId ? (
        slots.isPending ? (
          <LoadingState label="Finding times…" />
        ) : slots.isError ? (
          <ErrorState message="Could not load times." onRetry={() => slots.refetch()} />
        ) : slots.data.length === 0 ? (
          <EmptyState message="No free times on this day. Try another day." />
        ) : (
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
            {slots.data.map((s) => (
              <Pressable
                key={s.start_at}
                accessibilityRole="button"
                accessibilityState={{ selected: slot === s.start_at }}
                onPress={() => setSlot(s.start_at)}
                style={{
                  minHeight: MIN_TOUCH, minWidth: 92, alignItems: 'center', justifyContent: 'center',
                  borderRadius: 12, borderWidth: 1.5, borderColor: t.primary,
                  backgroundColor: slot === s.start_at ? t.primary : 'transparent',
                }}>
                <Text style={{ color: slot === s.start_at ? t.primaryText : t.primary, fontWeight: '700' }}>
                  {formatTime(s.start_at)}
                </Text>
              </Pressable>
            ))}
          </View>
        )
      ) : null}
      {error ? <Text accessibilityRole="alert" style={{ color: t.danger }}>{error}</Text> : null}
      <Button title="Confirm booking" disabled={!slot} loading={book.isPending} onPress={() => { setError(undefined); book.mutate(); }} />
    </ScrollView>
  );
}

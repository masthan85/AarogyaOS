import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { Alert, ScrollView, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import { getFollowUps, setFollowUpStatus } from '@/api/endpoints';
import { useAuth } from '@/auth/AuthProvider';
import { Button, Card, EmptyState, ErrorState, Lead, LoadingState, SectionTitle } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
import { addDays, toDateString } from '@/domain/dates';
import { can } from '@/domain/permissions';
import { groupFollowUps, KIND_LABEL } from '@/domain/worklists';

export function FollowUpsScreen() {
  const t = useTheme();
  const { me } = useAuth();
  const qc = useQueryClient();
  const canWrite = can(me, 'followup:write');
  const today = toDateString(new Date());
  const q = useQuery({
    queryKey: ['follow-ups'],
    queryFn: () => getFollowUps({ status: 'PENDING' }),
    gcTime: 0,
  });
  const update = useMutation({
    mutationFn: (v: { id: string; status: 'COMPLETED' | 'CANCELLED' }) => setFollowUpStatus(v.id, v.status),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['follow-ups'] }),
    onError: (e) => Alert.alert('Could not update', e instanceof ApiError ? e.message : 'Check your connection.'),
  });
  if (q.isPending) return <LoadingState label="Loading follow-ups…" />;
  if (q.isError) return <ErrorState message="Could not load follow-ups." onRetry={() => void q.refetch()} />;
  const groups = groupFollowUps(q.data, today, toDateString(addDays(new Date(), 7)));

  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md }}>
      <Lead>
        Patients a doctor asked to see again. Contact them using the details on their record; this screen does not message anyone.
      </Lead>
      {groups.length === 0 ? <EmptyState message="No follow-ups are waiting." /> : null}
      {groups.map((g) => (
        <View key={g.key} style={{ gap: space.sm }}>
          <SectionTitle>{`${g.title} (${g.rows.length})`}</SectionTitle>
          {g.rows.map((f) => (
            <Card key={f.id} title={`${KIND_LABEL[f.kind] ?? f.kind} · ${f.due_date}`}>
              <Text style={{ color: g.key === 'overdue' ? t.danger : t.text }}>{f.reason}</Text>
              <Button title="Open patient" variant="secondary" onPress={() => router.push(`/patients/${f.patient_id}`)} />
              {canWrite ? (
                <View style={{ gap: space.sm }}>
                  <Button title="Done" loading={update.isPending && update.variables?.id === f.id} onPress={() => update.mutate({ id: f.id, status: 'COMPLETED' })} />
                  <Button
                    title="Cancel follow-up"
                    variant="secondary"
                    onPress={() =>
                      Alert.alert('Cancel this follow-up?', 'It will drop off the list.', [
                        { text: 'Keep', style: 'cancel' },
                        { text: 'Cancel it', style: 'destructive', onPress: () => update.mutate({ id: f.id, status: 'CANCELLED' }) },
                      ])
                    }
                  />
                </View>
              ) : null}
            </Card>
          ))}
        </View>
      ))}
    </ScrollView>
  );
}

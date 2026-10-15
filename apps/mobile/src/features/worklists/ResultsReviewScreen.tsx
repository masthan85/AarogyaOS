import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { Alert, ScrollView, Text } from 'react-native';

import { getResultsAwaitingReview, reviewResult } from '@/api/endpoints';
import { ApiError } from '@/api/client';
import { Button, Card, EmptyState, ErrorState, LoadingState, StatusChip } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
import { formatDateTime } from '@/domain/dates';
import { describeValue, isCritical, reviewOrder } from '@/domain/worklists';

export function ResultsReviewScreen() {
  const t = useTheme();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['results-awaiting'], queryFn: getResultsAwaitingReview, gcTime: 0, refetchInterval: 60_000 });
  const review = useMutation({
    mutationFn: (id: string) => reviewResult(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['results-awaiting'] }),
    onError: (e) => Alert.alert('Could not mark as reviewed', e instanceof ApiError ? e.message : 'Check your connection.'),
  });
  if (q.isPending) return <LoadingState label="Loading results…" />;
  if (q.isError) return <ErrorState message="Could not load results." onRetry={() => void q.refetch()} />;
  const rows = reviewOrder(q.data);

  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md }}>
      <Text style={{ color: t.textMuted }}>
        Results for investigations you ordered that you have not yet reviewed. Critical values come first. Marking a result reviewed is
        your confirmation that you have looked at it; it does not tell the patient anything.
      </Text>
      {rows.length === 0 ? <EmptyState message="Nothing waiting for your review." /> : null}
      {rows.map((r) => (
        <Card key={r.id} title={r.test_name}>
          <Text style={{ color: isCritical(r) ? t.danger : t.text, fontWeight: '700', fontSize: 18 }}>{describeValue(r)}</Text>
          <StatusChip label={r.interpretation.replace('_', ' ').toLowerCase()} tone={isCritical(r) ? 'danger' : r.interpretation === 'NORMAL' ? 'success' : 'warning'} />
          {r.comment ? <Text style={{ color: t.textMuted }}>{r.comment}</Text> : null}
          <Text style={{ color: t.textMuted, fontSize: 12 }}>Reported {formatDateTime(r.reported_at)}</Text>
          <Button title="Open patient" variant="secondary" onPress={() => router.push(`/patients/${r.patient_id}`)} />
          <Button title="Mark as reviewed" loading={review.isPending && review.variables === r.id} onPress={() => review.mutate(r.id)} />
        </Card>
      ))}
    </ScrollView>
  );
}

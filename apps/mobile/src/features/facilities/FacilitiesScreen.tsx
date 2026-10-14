import { useQuery } from '@tanstack/react-query';
import { FlatList, Text } from 'react-native';

import { getFacilities } from '@/api/endpoints';
import { Card, EmptyState, ErrorState, LoadingState, StatusChip } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';

export function FacilitiesScreen() {
  const t = useTheme();
  const q = useQuery({ queryKey: ['facilities'], queryFn: getFacilities });

  if (q.isPending) return <LoadingState label="Loading facilities…" />;
  if (q.isError) return <ErrorState message="Could not load facilities." onRetry={() => q.refetch()} />;
  return (
    <FlatList
      data={q.data}
      keyExtractor={(f) => f.id}
      contentContainerStyle={{ padding: space.md, gap: space.md }}
      ListEmptyComponent={<EmptyState message="No facilities yet." />}
      refreshing={q.isRefetching}
      onRefresh={() => q.refetch()}
      renderItem={({ item }) => (
        <Card title={item.name}>
          <Text style={{ color: t.textMuted }}>
            {item.code} · {item.kind.toLowerCase()} · {item.timezone}
          </Text>
          <StatusChip label={item.status} tone={item.status === 'ACTIVE' ? 'success' : 'warning'} />
        </Card>
      )}
    />
  );
}

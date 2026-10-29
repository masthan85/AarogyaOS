import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Alert, ScrollView, Text } from 'react-native';

import { ApiError } from '@/api/client';
import { arrangeCover, endCover, getColleagues, getCover } from '@/api/endpoints';
import { useAuth } from '@/auth/AuthProvider';
import { Button, Card, ChoiceChips, EmptyState, Lead, LoadingState, SectionTitle, StatusChip, TextField } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
import { addDays, toDateString } from '@/domain/dates';
import { coverProblem } from '@/domain/worklists';

export function CoverScreen() {
  const t = useTheme();
  const { me } = useAuth();
  const qc = useQueryClient();
  const today = toDateString(new Date());
  const colleagues = useQuery({ queryKey: ['colleagues'], queryFn: getColleagues, gcTime: 0 });
  const cover = useQuery({ queryKey: ['cover'], queryFn: getCover, gcTime: 0 });
  const [to, setTo] = useState<string>();
  const [from, setFrom] = useState(today);
  const [until, setUntil] = useState(toDateString(addDays(new Date(), 2)));
  const [error, setError] = useState<string>();
  const fail = (e: unknown) => Alert.alert('Could not complete', e instanceof ApiError ? e.message : 'Check your connection.');
  const refresh = () => void qc.invalidateQueries({ queryKey: ['cover'] });
  const create = useMutation({ mutationFn: arrangeCover, onSuccess: refresh, onError: fail });
  const end = useMutation({ mutationFn: endCover, onSuccess: refresh, onError: fail });

  const submit = () => {
    const problem = !to ? 'Choose a colleague.' : coverProblem(from, until, today);
    setError(problem ?? undefined);
    if (!problem && to) create.mutate({ to_user_id: to, starts_on: from, ends_on: until });
  };

  if (colleagues.isPending || cover.isPending) return <LoadingState />;
  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md }} keyboardShouldPersistTaps="handled">
      <Lead>
        Ask a colleague to review your investigation results while you are away. They will see your results in their review list for
        those dates only, and each review is recorded under their name. Your patients and orders stay yours.
      </Lead>
      <SectionTitle>Arrangements</SectionTitle>
      {cover.data?.length === 0 ? <EmptyState message="No cover arranged." /> : null}
      {cover.data?.map((c) => {
        const mineOut = c.from_user_id === me?.id;
        return (
          <Card key={c.id} title={mineOut ? `${c.to_name} covers you` : `You cover ${c.from_name}`}>
            <Text style={{ color: t.text }}>{c.starts_on} to {c.ends_on}</Text>
            <StatusChip label={c.active ? 'Active now' : 'Not active'} tone={c.active ? 'success' : 'neutral'} />
            {c.active || c.starts_on > today ? (
              <Button title="End cover" variant="secondary" loading={end.isPending && end.variables === c.id} onPress={() => end.mutate(c.id)} />
            ) : null}
          </Card>
        );
      })}
      <SectionTitle>Arrange cover</SectionTitle>
      {colleagues.data?.length === 0 ? <EmptyState message="There are no other doctors to ask." /> : null}
      <ChoiceChips label="Colleague" value={to} onChange={setTo} options={(colleagues.data ?? []).map((c) => ({ value: c.user_id, label: c.name }))} />
      <TextField label="From (YYYY-MM-DD)" value={from} onChangeText={setFrom} autoCapitalize="none" />
      <TextField label="Until (YYYY-MM-DD)" value={until} onChangeText={setUntil} autoCapitalize="none" />
      {error ? <Text style={{ color: t.danger }}>{error}</Text> : null}
      <Button title="Arrange cover" loading={create.isPending} onPress={submit} />
    </ScrollView>
  );
}

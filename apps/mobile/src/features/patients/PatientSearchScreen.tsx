import { useQuery } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useState } from 'react';
import { FlatList, Pressable, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import { type PatientSearch, searchPatients } from '@/api/endpoints';
import type { PatientHit } from '@/api/schemas';
import { useAuth } from '@/auth/AuthProvider';
import { Button, Card, ChoiceChips, EmptyState, ErrorState, LoadingState, TextField } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
import { can } from '@/domain/permissions';

type Mode = 'name' | 'mobile' | 'mrn';
const PLACEHOLDER: Record<Mode, string> = {
  name: 'At least 3 letters of the name',
  mobile: '10-digit mobile number',
  mrn: 'e.g. P0000123',
};

export function PatientHitRow({ p, onPress }: { p: PatientHit; onPress: () => void }) {
  const t = useTheme();
  return (
    <Pressable accessibilityRole="button" onPress={onPress}>
      <Card>
        <Text style={{ color: t.text, fontSize: 17, fontWeight: '700' }}>{p.full_name}</Text>
        <Text style={{ color: t.textMuted }}>
          {p.mrn} · {p.age_years ?? '?'} yrs · {p.administrative_gender}
          {p.mobile_masked ? ` · ${p.mobile_masked}` : ''}
        </Text>
      </Card>
    </Pressable>
  );
}

export function PatientSearchScreen() {
  const t = useTheme();
  const { me } = useAuth();
  const [mode, setMode] = useState<Mode>('name');
  const [text, setText] = useState('');
  const [submitted, setSubmitted] = useState<PatientSearch | null>(null);

  // gcTime 0: search results are PHI, so they are not kept in the cache once the screen closes.
  const results = useQuery({
    queryKey: ['patient-search', submitted],
    queryFn: () => searchPatients(submitted ?? {}),
    enabled: submitted !== null,
    gcTime: 0,
    retry: false,
  });
  const canOpen = can(me, 'patient:read');

  return (
    <View style={{ flex: 1 }}>
      <View style={{ padding: space.md, gap: space.md }}>
        <ChoiceChips
          options={[
            { value: 'name', label: 'Name' },
            { value: 'mobile', label: 'Mobile' },
            { value: 'mrn', label: 'MRN' },
          ]}
          value={mode}
          onChange={(m) => {
            setMode(m);
            setText('');
            setSubmitted(null);
          }}
        />
        <TextField
          label="Find a patient"
          placeholder={PLACEHOLDER[mode]}
          value={text}
          onChangeText={setText}
          keyboardType={mode === 'mobile' ? 'phone-pad' : 'default'}
          autoCapitalize={mode === 'mrn' ? 'characters' : 'words'}
          returnKeyType="search"
          onSubmitEditing={() => text.trim() && setSubmitted({ [mode]: text.trim() })}
        />
        <Button title="Search" onPress={() => text.trim() && setSubmitted({ [mode]: text.trim() })} />
        {can(me, 'patient:create') ? (
          <Button title="Register new patient" variant="secondary" onPress={() => router.push('/patients/new')} />
        ) : null}
      </View>

      {results.isFetching ? (
        <LoadingState label="Searching…" />
      ) : results.isError ? (
        <ErrorState
          message={results.error instanceof ApiError ? results.error.message : 'Search failed. Try again.'}
        />
      ) : results.data ? (
        <FlatList
          data={results.data}
          keyExtractor={(p) => p.id}
          contentContainerStyle={{ padding: space.md, gap: space.md }}
          ListEmptyComponent={<EmptyState message="No matching patient. Check the spelling or register a new patient." />}
          renderItem={({ item }) => (
            <PatientHitRow p={item} onPress={() => canOpen && router.push(`/patients/${item.id}`)} />
          )}
        />
      ) : (
        <Text style={{ color: t.textMuted, paddingHorizontal: space.md }}>
          Search by name, mobile number or MRN. Results show only what you need to pick the right person.
        </Text>
      )}
    </View>
  );
}

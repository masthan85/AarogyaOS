import { Stack } from 'expo-router';

import { useTheme } from '@/design-system/tokens';

export default function AppLayout() {
  const t = useTheme();
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: t.surface },
        headerTintColor: t.text,
        contentStyle: { backgroundColor: t.background },
      }}>
      <Stack.Screen name="index" options={{ title: 'AarogyaOS' }} />
      <Stack.Screen name="facilities" options={{ title: 'Facilities' }} />
      <Stack.Screen name="patients/index" options={{ title: 'Patients' }} />
      <Stack.Screen name="patients/new" options={{ title: 'New patient' }} />
      <Stack.Screen name="patients/[id]" options={{ title: 'Patient' }} />
      <Stack.Screen name="appointments/index" options={{ title: 'Appointments' }} />
      <Stack.Screen name="appointments/book" options={{ title: 'Book appointment' }} />
      <Stack.Screen name="queue" options={{ title: 'Queue' }} />
      <Stack.Screen name="settings" options={{ title: 'Settings' }} />
    </Stack>
  );
}

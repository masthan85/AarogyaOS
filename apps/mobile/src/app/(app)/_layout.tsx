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
      <Stack.Screen name="index" options={{ title: 'AarogyaOS', headerStyle: { backgroundColor: t.hero }, headerTintColor: t.heroText, headerShadowVisible: false }} />
      <Stack.Screen name="facilities" options={{ title: 'Facilities' }} />
      <Stack.Screen name="patients/index" options={{ title: 'Patients' }} />
      <Stack.Screen name="patients/new" options={{ title: 'New patient' }} />
      <Stack.Screen name="patients/[id]" options={{ title: 'Patient' }} />
      <Stack.Screen name="appointments/index" options={{ title: 'Appointments' }} />
      <Stack.Screen name="appointments/book" options={{ title: 'Book appointment' }} />
      <Stack.Screen name="results" options={{ title: 'Results to review' }} />
      <Stack.Screen name="pharmacy" options={{ title: 'Pharmacy' }} />
      <Stack.Screen name="cover" options={{ title: 'Cover while away' }} />
      <Stack.Screen name="follow-ups" options={{ title: 'Follow-ups' }} />
      <Stack.Screen name="lab" options={{ title: 'Orders and results' }} />
      <Stack.Screen name="queue" options={{ title: 'Queue' }} />
      <Stack.Screen name="triage/[appointmentId]" options={{ title: 'Triage' }} />
      <Stack.Screen name="consultation/[id]" options={{ title: 'Consultation' }} />
      <Stack.Screen name="consent/[patientId]" options={{ title: 'Consent' }} />
      <Stack.Screen name="settings" options={{ title: 'Settings' }} />
      <Stack.Screen name="admin/index" options={{ title: 'Administration' }} />
      <Stack.Screen name="admin/policy" options={{ title: 'Organisation settings' }} />
      <Stack.Screen name="admin/staff" options={{ title: 'Staff and doctors' }} />
      <Stack.Screen name="admin/templates" options={{ title: 'Note layouts' }} />
      <Stack.Screen name="admin/knowledge" options={{ title: 'Reference library' }} />
      <Stack.Screen name="admin/activity" options={{ title: 'Usage and audit' }} />
    </Stack>
  );
}

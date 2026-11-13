import { Stack } from 'expo-router';
import { useWindowDimensions, View } from 'react-native';

import { layout, useTheme } from '@/design-system/tokens';
import { Sidebar } from '@/features/shell/Sidebar';

export default function AppLayout() {
  const t = useTheme();
  const { width } = useWindowDimensions();
  // Wide screens (desktop browsers, landscape tablets) get a sidebar and a readable column;
  // phones keep the full-width stack and navigate from the home screen.
  const wide = width >= layout.wide;
  const stack = (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: wide ? t.background : t.surface },
        headerTintColor: t.text,
        headerTitleStyle: { fontWeight: '700' },
        headerShadowVisible: !wide,
        contentStyle: { backgroundColor: t.background },
      }}>
      <Stack.Screen name="index" options={{ title: 'AarogyaOS', headerShown: !wide, headerStyle: { backgroundColor: t.hero }, headerTintColor: t.heroText, headerShadowVisible: false }} />
      <Stack.Screen name="facilities" options={{ title: 'Facilities' }} />
      <Stack.Screen name="patients/index" options={{ title: 'Patients' }} />
      <Stack.Screen name="patients/new" options={{ title: 'New patient' }} />
      <Stack.Screen name="patients/[id]" options={{ title: 'Patient' }} />
      <Stack.Screen name="appointments/index" options={{ title: 'Appointments' }} />
      <Stack.Screen name="appointments/book" options={{ title: 'Book appointment' }} />
      <Stack.Screen name="results" options={{ title: 'Results to review' }} />
      <Stack.Screen name="billing/index" options={{ title: 'Billing' }} />
      <Stack.Screen name="billing/[id]" options={{ title: 'Invoice' }} />
      <Stack.Screen name="billing/prices" options={{ title: 'Price list' }} />
      <Stack.Screen name="billing/day" options={{ title: 'End of day' }} />
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
  if (!wide) return stack;
  return (
    <View style={{ flex: 1, flexDirection: 'row', backgroundColor: t.background }}>
      <Sidebar />
      <View style={{ flex: 1 }}>
        <View style={{ flex: 1, width: '100%', maxWidth: layout.content, alignSelf: 'center' }}>{stack}</View>
      </View>
    </View>
  );
}

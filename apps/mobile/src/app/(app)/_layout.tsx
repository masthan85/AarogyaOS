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
      <Stack.Screen name="settings" options={{ title: 'Settings' }} />
    </Stack>
  );
}

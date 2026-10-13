import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { View } from 'react-native';

import { AuthProvider, useAuth } from '@/auth/AuthProvider';
import { Button, ErrorState, LoadingState } from '@/design-system/components';
import { useTheme } from '@/design-system/tokens';

function Gate() {
  const { status, signOut, retryBoot } = useAuth();
  const t = useTheme();

  if (status === 'booting') return <Centered><LoadingState label="Starting AarogyaOS…" /></Centered>;
  if (status === 'locked' || status === 'offline') {
    return (
      <Centered>
        <ErrorState
          message={
            status === 'locked'
              ? 'AarogyaOS is locked. Authenticate to continue.'
              : 'Cannot reach the server. Check your connection.'
          }
          onRetry={retryBoot}
        />
        <View style={{ padding: 16 }}>
          <Button title="Sign out" variant="secondary" onPress={signOut} />
        </View>
      </Centered>
    );
  }

  const signedIn = status === 'signedIn';
  return (
    <>
      <StatusBar style="auto" />
      <Stack screenOptions={{ contentStyle: { backgroundColor: t.background } }}>
        <Stack.Protected guard={signedIn}>
          <Stack.Screen name="(app)" options={{ headerShown: false }} />
        </Stack.Protected>
        <Stack.Protected guard={!signedIn}>
          <Stack.Screen name="login" options={{ headerShown: false }} />
        </Stack.Protected>
      </Stack>
    </>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  const t = useTheme();
  return <View style={{ flex: 1, justifyContent: 'center', backgroundColor: t.background }}>{children}</View>;
}

export default function RootLayout() {
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 30_000 } } }),
  );
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Gate />
      </AuthProvider>
    </QueryClientProvider>
  );
}

import { useEffect, useState } from 'react';
import { ScrollView, Switch, Text, View } from 'react-native';

import { useAuth } from '@/auth/AuthProvider';
import { Button, Card } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
import {
  biometricsAvailable,
  isBiometricUnlockEnabled,
  promptBiometricUnlock,
  setBiometricUnlockEnabled,
} from '@/services/biometrics';

export function SettingsScreen() {
  const t = useTheme();
  const { me, signOut } = useAuth();
  const [available, setAvailable] = useState(false);
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    void (async () => {
      setAvailable(await biometricsAvailable());
      setEnabled(await isBiometricUnlockEnabled());
    })();
  }, []);

  const toggle = async (next: boolean) => {
    // Require a successful prompt before turning the lock on, so users cannot lock themselves out.
    if (next && !(await promptBiometricUnlock())) return;
    await setBiometricUnlockEnabled(next);
    setEnabled(next);
  };

  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md }}>
      <Card title="Account">
        <Text style={{ color: t.text }}>{me?.full_name}</Text>
        <Text style={{ color: t.textMuted }}>{me?.email}</Text>
      </Card>
      <Card title="Security">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <Text style={{ color: t.text, flex: 1 }}>
            {available ? 'Require biometrics when opening the app' : 'Biometrics not set up on this device'}
          </Text>
          <Switch value={enabled} disabled={!available} onValueChange={toggle} accessibilityLabel="Biometric unlock" />
        </View>
      </Card>
      <Button title="Sign out" variant="danger" onPress={signOut} />
    </ScrollView>
  );
}

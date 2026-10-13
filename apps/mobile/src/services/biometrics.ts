import * as LocalAuthentication from 'expo-local-authentication';
import * as SecureStore from 'expo-secure-store';

const PREF_KEY = 'aarogya.biometric.enabled';

export async function biometricsAvailable(): Promise<boolean> {
  const [hardware, enrolled] = await Promise.all([
    LocalAuthentication.hasHardwareAsync(),
    LocalAuthentication.isEnrolledAsync(),
  ]);
  return hardware && enrolled;
}

export async function isBiometricUnlockEnabled(): Promise<boolean> {
  return (await SecureStore.getItemAsync(PREF_KEY)) === '1';
}

export async function setBiometricUnlockEnabled(enabled: boolean): Promise<void> {
  if (enabled) await SecureStore.setItemAsync(PREF_KEY, '1');
  else await SecureStore.deleteItemAsync(PREF_KEY);
}

/** Local device unlock gate. It does not replace server authentication. */
export async function promptBiometricUnlock(): Promise<boolean> {
  const result = await LocalAuthentication.authenticateAsync({
    promptMessage: 'Unlock AarogyaOS',
    cancelLabel: 'Cancel',
    disableDeviceFallback: false,
  });
  return result.success;
}

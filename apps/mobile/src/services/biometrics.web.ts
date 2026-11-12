// Browser build: there is no device unlock to rely on, so biometric unlock is never offered.

export async function biometricsAvailable(): Promise<boolean> {
  return false;
}

export async function isBiometricUnlockEnabled(): Promise<boolean> {
  return false;
}

export async function setBiometricUnlockEnabled(_enabled: boolean): Promise<void> {}

export async function promptBiometricUnlock(): Promise<boolean> {
  return false;
}

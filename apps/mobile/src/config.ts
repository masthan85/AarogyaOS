// Android emulators reach the host machine at 10.0.2.2. Override per environment with
// EXPO_PUBLIC_API_URL. Never put secrets in EXPO_PUBLIC_* variables: they ship in the app.
export const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://10.0.2.2:8000';
export const API_PREFIX = '/api/v1';

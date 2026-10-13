import * as SecureStore from 'expo-secure-store';

export type Tokens = { accessToken: string; refreshToken: string };

export interface TokenStore {
  load(): Promise<Tokens | null>;
  save(tokens: Tokens): Promise<void>;
  clear(): Promise<void>;
}

const KEY = 'aarogya.tokens.v1';

/** Tokens live only in the iOS Keychain / Android Keystore via expo-secure-store. */
export const secureTokenStore: TokenStore = {
  async load() {
    const raw = await SecureStore.getItemAsync(KEY);
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw) as Partial<Tokens>;
      return parsed.accessToken && parsed.refreshToken
        ? { accessToken: parsed.accessToken, refreshToken: parsed.refreshToken }
        : null;
    } catch {
      return null;
    }
  },
  async save(tokens) {
    await SecureStore.setItemAsync(KEY, JSON.stringify(tokens));
  },
  async clear() {
    await SecureStore.deleteItemAsync(KEY);
  },
};

import type { TokenStore, Tokens } from './token-store';

let current: Tokens | null = null;

/**
 * Browser build, for development and demonstrations. A browser has no keystore, and web storage
 * is readable by any script on the page, so tokens stay in memory: reloading the page signs out.
 */
export const secureTokenStore: TokenStore = {
  async load() {
    return current;
  },
  async save(tokens) {
    current = tokens;
  },
  async clear() {
    current = null;
  },
};

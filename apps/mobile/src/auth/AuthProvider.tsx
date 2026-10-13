import { useQueryClient } from '@tanstack/react-query';
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { ApiError } from '@/api/client';
import { getMe, login, logout, onSessionExpired } from '@/api/endpoints';
import type { Me } from '@/api/schemas';
import { isBiometricUnlockEnabled, promptBiometricUnlock } from '@/services/biometrics';
import { secureTokenStore } from '@/services/token-store';

type Status = 'booting' | 'locked' | 'offline' | 'signedOut' | 'signedIn';

type AuthState = {
  status: Status;
  me: Me | null;
  signIn: (input: { organisationSlug?: string; email: string; password: string }) => Promise<void>;
  signOut: () => Promise<void>;
  retryBoot: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<Status>('booting');
  const [me, setMe] = useState<Me | null>(null);
  const [attempt, setAttempt] = useState(0);

  const endSession = useCallback(() => {
    setMe(null);
    setStatus('signedOut');
    queryClient.clear(); // no cached patient/clinical data survives sign-out
  }, [queryClient]);

  useEffect(() => {
    onSessionExpired(endSession);
  }, [endSession]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const tokens = await secureTokenStore.load();
      if (cancelled) return;
      if (!tokens) return setStatus('signedOut');
      if (await isBiometricUnlockEnabled()) {
        const ok = await promptBiometricUnlock();
        if (cancelled) return;
        if (!ok) return setStatus('locked');
      }
      try {
        const profile = await getMe();
        if (cancelled) return;
        setMe(profile);
        setStatus('signedIn');
      } catch (err) {
        if (cancelled) return;
        // Only a definite 401 means signed out; anything else is connectivity.
        if (err instanceof ApiError && err.status === 401) setStatus('signedOut');
        else setStatus('offline');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const signIn: AuthState['signIn'] = useCallback(async ({ organisationSlug, email, password }) => {
    const pair = await login({
      organisation_slug: organisationSlug || undefined,
      email,
      password,
    });
    await secureTokenStore.save({ accessToken: pair.access_token, refreshToken: pair.refresh_token });
    setMe(await getMe());
    setStatus('signedIn');
  }, []);

  const signOut = useCallback(async () => {
    const tokens = await secureTokenStore.load();
    try {
      if (tokens) await logout(tokens.refreshToken);
    } catch {
      /* best effort: local sign-out must succeed even offline */
    }
    await secureTokenStore.clear();
    endSession();
  }, [endSession]);

  const retryBoot = useCallback(() => {
    setStatus('booting');
    setAttempt((n) => n + 1);
  }, []);

  const value = useMemo(
    () => ({ status, me, signIn, signOut, retryBoot }),
    [status, me, signIn, signOut, retryBoot],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}

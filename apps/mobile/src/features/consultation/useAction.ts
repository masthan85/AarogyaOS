import { useCallback, useState } from 'react';
import { Alert } from 'react-native';

import { ApiError } from '@/api/client';

/**
 * Runs a save with a pending flag and a plain-language failure message.
 * Clinical writes are never queued offline: if the network drops, the clinician is told that
 * nothing was saved and can retry, rather than assuming it went through.
 */
export function useAction<A extends unknown[], R>(fn: (...args: A) => Promise<R>, onDone?: (r: R) => void) {
  const [pending, setPending] = useState(false);
  const run = useCallback(
    async (...args: A): Promise<R | undefined> => {
      setPending(true);
      try {
        const result = await fn(...args);
        onDone?.(result);
        return result;
      } catch (e) {
        Alert.alert('Not saved', e instanceof ApiError ? e.message : 'Check your connection. Nothing was saved.');
        return undefined;
      } finally {
        setPending(false);
      }
    },
    [fn, onDone],
  );
  return { run, pending };
}

import { useSyncExternalStore } from 'react';

/**
 * Whether the last request reached the server. This is about the API, not the network in general:
 * Wi-Fi with no route to the clinic's server is still "not connected" for anyone trying to save.
 * Nothing is queued while disconnected, so the app must say plainly that work is not being saved.
 */
let reachable = true;
const listeners = new Set<() => void>();

export function reportReachable(ok: boolean): void {
  if (ok === reachable) return;
  reachable = ok;
  listeners.forEach((l) => l());
}

export const isReachable = (): boolean => reachable;

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

export const useServerReachable = (): boolean => useSyncExternalStore(subscribe, isReachable, isReachable);

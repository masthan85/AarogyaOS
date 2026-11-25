import { allowScreenCaptureAsync, preventScreenCaptureAsync } from 'expo-screen-capture';
import { useEffect } from 'react';

const TAG = 'aarogya-signed-in';

/**
 * While mounted, stop the screen being captured. On Android this blocks screenshots and screen
 * recording and blanks the app in the recent-apps view. On iOS an app cannot stop a screenshot;
 * the content is hidden from screen recordings and mirroring instead.
 */
export function useScreenGuard(on: boolean): void {
  useEffect(() => {
    if (!on) return undefined;
    preventScreenCaptureAsync(TAG).catch(() => undefined);
    return () => {
      allowScreenCaptureAsync(TAG).catch(() => undefined);
    };
  }, [on]);
}

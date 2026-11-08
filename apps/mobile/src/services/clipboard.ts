import * as Clipboard from 'expo-clipboard';

export const CLEAR_AFTER_MS = 60_000;

type Board = { read: () => Promise<string>; write: (text: string) => Promise<unknown> };
const expoBoard: Board = { read: () => Clipboard.getStringAsync(), write: (t) => Clipboard.setStringAsync(t) };

/**
 * Copies clinical text and clears it again after a minute, but only if the clipboard still holds exactly
 * what we put there, so something the person copied in the meantime is never erased.
 * Timers do not survive the app being closed; the notice shown to the user says so.
 */
export async function copyThenClear(
  text: string,
  board: Board = expoBoard,
  after: number = CLEAR_AFTER_MS,
  schedule: (fn: () => void, ms: number) => unknown = setTimeout,
): Promise<void> {
  await board.write(text);
  schedule(() => {
    void board.read().then((now) => (now === text ? board.write('') : undefined)).catch(() => undefined);
  }, after);
}

/**
 * Plays a WAV the server generated (a doctor-approved document read aloud). The audio is written to
 * the app's cache folder only for as long as it plays and is deleted afterwards.
 *
 * Unit-tested only for the decision logic; never run on a device here.
 */
export type Playback = { stop(): void };

export async function playWav(bytes: ArrayBuffer, onFinished: () => void): Promise<Playback> {
  // Loaded lazily: the native modules do not exist under Jest, on web or in Expo Go builds without them.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { createAudioPlayer } = require('expo-audio');
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { File, Paths } = require('expo-file-system');
  const file = new File(Paths.cache, `read-aloud-${Date.now()}.wav`);
  file.create({ overwrite: true });
  file.write(new Uint8Array(bytes));
  const player = createAudioPlayer(file.uri);
  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    try {
      player.remove();
      file.delete();
    } catch {
      /* already gone */
    }
    onFinished();
  };
  player.addListener('playbackStatusUpdate', (status: { didJustFinish?: boolean }) => {
    if (status.didJustFinish) finish();
  });
  player.play();
  return { stop: finish };
}

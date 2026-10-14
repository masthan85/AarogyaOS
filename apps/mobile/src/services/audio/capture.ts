/**
 * Microphone capture behind an interface.
 *
 * What exists today:
 *  - SimulatedCapture: silence at real-time pace, DEVELOPMENT ONLY. It lets the whole pipeline
 *    be exercised (gateway, consent enforcement, transcript, speaker assignment) without a
 *    microphone. It never contains real speech and is not available in release builds.
 *  - MicrophoneCapture: the real thing needs a native module that streams 16 kHz mono PCM16
 *    (candidates: @siteed/audio-studio, react-native-live-audio-stream). None is installed
 *    because none could be verified on a device in this build; see docs/SPEECH_ARCHITECTURE.md.
 *    Until then Start is disabled in release builds and the clinician documents manually.
 */

export type FrameHandler = (frame: Uint8Array) => void;

export interface AudioCapture {
  readonly kind: 'simulated' | 'microphone';
  readonly running: boolean;
  start(onFrame: FrameHandler): Promise<void>;
  stop(): Promise<void>;
}

export class CaptureUnavailableError extends Error {
  constructor(message = 'Live microphone streaming is not available in this build.') {
    super(message);
    this.name = 'CaptureUnavailableError';
  }
}

/** 16 kHz mono PCM16 = 32,000 bytes per second. */
export const BYTES_PER_SECOND = 32_000;
export const SIMULATED_FRAME_MS = 250;

export class SimulatedCapture implements AudioCapture {
  readonly kind = 'simulated' as const;
  private timer: ReturnType<typeof setInterval> | null = null;

  get running(): boolean {
    return this.timer !== null;
  }

  async start(onFrame: FrameHandler): Promise<void> {
    if (this.timer) return;
    const frame = new Uint8Array((BYTES_PER_SECOND * SIMULATED_FRAME_MS) / 1000); // silence
    this.timer = setInterval(() => onFrame(frame), SIMULATED_FRAME_MS);
  }

  async stop(): Promise<void> {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }
}

export class MicrophoneCapture implements AudioCapture {
  readonly kind = 'microphone' as const;
  readonly running = false;

  async start(): Promise<void> {
    throw new CaptureUnavailableError();
  }

  async stop(): Promise<void> {}
}

export const simulatedAudioAllowed = (): boolean =>
  __DEV__ || process.env.EXPO_PUBLIC_SIMULATED_AUDIO === '1';

export function createCapture(): AudioCapture {
  return simulatedAudioAllowed() ? new SimulatedCapture() : new MicrophoneCapture();
}

/**
 * Microphone capture behind an interface.
 *
 * What exists today:
 *  - SimulatedCapture: silence at real-time pace, DEVELOPMENT ONLY. It lets the whole pipeline
 *    be exercised (gateway, consent enforcement, transcript, speaker assignment) without a
 *    microphone. It never contains real speech and is not available in release builds.
 *  - MicrophoneCapture: streams 16 kHz mono PCM16 through @siteed/audio-studio (pinned). It is
 *    unit-tested against a fake backend only; it has NOT been run on a device here, so test it on
 *    hardware (docs/DEVICE_TEST_PLAN.md) before clinical use. Where the native module is missing
 *    (Expo Go, web) it refuses with an explanation and the clinician documents manually.
 */

export type FrameHandler = (frame: Uint8Array) => void;

export interface AudioCapture {
  readonly kind: 'simulated' | 'microphone';
  readonly running: boolean;
  /** `onInterrupt` fires if the OS takes the microphone away (a call, another app). */
  start(onFrame: FrameHandler, onInterrupt?: (reason: string) => void): Promise<void>;
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

/** What the microphone needs from a native module. Injectable so the logic is testable off-device. */
export interface MicBackend {
  requestPermission(): Promise<boolean>;
  /** Starts streaming; `onChunk` gets base64 PCM16 and `onInterrupt` fires when the OS takes the mic. */
  start(onChunk: (base64Pcm: string) => void, onInterrupt: (reason: string) => void): Promise<void>;
  stop(): Promise<void>;
}

const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
const B64_LOOKUP: Record<string, number> = Object.fromEntries([...B64].map((c, i) => [c, i]));

export function base64ToBytes(b64: string): Uint8Array {
  const clean = b64.replace(/[\s=]+/g, '');
  const out = new Uint8Array(Math.floor((clean.length * 3) / 4));
  let o = 0;
  for (let i = 0; i < clean.length; i += 4) {
    const a = B64_LOOKUP[clean[i]];
    const b = B64_LOOKUP[clean[i + 1]];
    const c = i + 2 < clean.length ? B64_LOOKUP[clean[i + 2]] : 0;
    const d = i + 3 < clean.length ? B64_LOOKUP[clean[i + 3]] : 0;
    if (a === undefined || b === undefined || c === undefined || d === undefined) {
      throw new Error('Invalid audio data');
    }
    out[o++] = (a << 2) | (b >> 4);
    if (i + 2 < clean.length) out[o++] = ((b & 15) << 4) | (c >> 2);
    if (i + 3 < clean.length) out[o++] = ((c & 3) << 6) | d;
  }
  return out;
}

/**
 * The recording settings. Audio is streamed and NOT kept on the phone: `output.primary.enabled`
 * is false because the library writes a WAV file by default, and a consultation recording must
 * not sit in app storage. Notifications, background capture and device detection are off in
 * app.json, so recording only runs while the consultation screen is in the foreground.
 */
export const MIC_CONFIG = {
  sampleRate: 16000,
  channels: 1,
  encoding: 'pcm_16bit',
  interval: 250,
  keepAwake: true,
  showNotification: false,
  enableProcessing: false,
  output: { primary: { enabled: false }, compressed: { enabled: false } },
} as const;

/** Interruption reasons after which the mic is no longer ours (a call, another app, a device loss). */
const LOST = new Set(['audioFocusLoss', 'phoneCall', 'recordingStopped', 'deviceDisconnected']);
export const micWasLost = (reason: string): boolean => LOST.has(reason);

/**
 * Real microphone capture through @siteed/audio-studio (pinned to 3.2.1). **Never run on a device
 * in this repository's build environment**: test it on target Android and iOS hardware (see
 * docs/DEVICE_TEST_PLAN.md) before any clinical use.
 */
export class MicrophoneCapture implements AudioCapture {
  readonly kind = 'microphone' as const;
  private active = false;
  private started = false; // the native recorder may still be open after the OS took the mic

  constructor(private readonly backend: MicBackend = nativeBackend()) {}

  get running(): boolean {
    return this.active;
  }

  async start(onFrame: FrameHandler, onInterrupt?: (reason: string) => void): Promise<void> {
    if (this.active) return;
    if (!(await this.backend.requestPermission())) {
      throw new CaptureUnavailableError('Microphone permission was not granted. Allow it in Settings to record.');
    }
    await this.backend.start(
      (b64) => {
        if (!this.active) return; // late chunk after stop: drop it
        try {
          const bytes = base64ToBytes(b64);
          if (bytes.length > 0) onFrame(bytes);
        } catch {
          // a corrupt chunk is skipped; the server rejects malformed audio anyway
        }
      },
      (reason) => {
        if (micWasLost(reason)) {
          this.active = false;
          onInterrupt?.(reason);
        }
      },
    );
    this.started = true;
    this.active = true;
  }

  async stop(): Promise<void> {
    this.active = false;
    if (!this.started) return;
    this.started = false;
    try {
      await this.backend.stop();
    } catch {
      // the OS may already have stopped it; either way nothing is capturing now
    }
  }
}

/** Loaded lazily: the native module does not exist in Expo Go, on web or under Jest. */
class NativeBackend implements MicBackend {
  private subscriptions: { remove(): void }[] = [];

  private load(): { mod: any; emitter: any } {
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const mod = require('@siteed/audio-studio').AudioStudioModule;
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const { LegacyEventEmitter } = require('expo-modules-core');
      return { mod, emitter: new LegacyEventEmitter(mod) };
    } catch {
      throw new CaptureUnavailableError(
        'Microphone streaming needs a development or release build of the app (it does not work in Expo Go).',
      );
    }
  }

  async requestPermission(): Promise<boolean> {
    const result = await this.load().mod.requestPermissionsAsync();
    return !!result?.granted;
  }

  async start(onChunk: (b64: string) => void, onInterrupt: (reason: string) => void): Promise<void> {
    const { mod, emitter } = this.load();
    this.subscriptions = [
      emitter.addListener('AudioData', (e: { encoded?: string; deltaSize?: number }) => {
        if (e.encoded && e.deltaSize !== 0) onChunk(e.encoded);
      }),
      emitter.addListener('onRecordingInterrupted', (e: { reason: string }) => onInterrupt(e.reason)),
    ];
    try {
      await mod.startRecording({ ...MIC_CONFIG });
    } catch (e) {
      this.release();
      throw e;
    }
  }

  async stop(): Promise<void> {
    this.release();
    await this.load().mod.stopRecording();
  }

  private release(): void {
    for (const s of this.subscriptions) s.remove();
    this.subscriptions = [];
  }
}

const nativeBackend = (): MicBackend => new NativeBackend();

export const simulatedAudioAllowed = (): boolean =>
  __DEV__ || process.env.EXPO_PUBLIC_SIMULATED_AUDIO === '1';

/** Development builds use the simulator unless EXPO_PUBLIC_USE_MICROPHONE=1 asks for the real mic. */
export const captureKind = (): 'simulated' | 'microphone' =>
  simulatedAudioAllowed() && process.env.EXPO_PUBLIC_USE_MICROPHONE !== '1' ? 'simulated' : 'microphone';

export function createCapture(): AudioCapture {
  return captureKind() === 'simulated' ? new SimulatedCapture() : new MicrophoneCapture();
}

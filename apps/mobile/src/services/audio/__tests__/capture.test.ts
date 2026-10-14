import {
  base64ToBytes,
  BYTES_PER_SECOND,
  CaptureUnavailableError,
  MIC_CONFIG,
  type MicBackend,
  MicrophoneCapture,
  SimulatedCapture,
} from '../capture';

describe('SimulatedCapture (development only)', () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it('produces silence at exactly real-time pace', async () => {
    const cap = new SimulatedCapture();
    let bytes = 0;
    let nonZero = 0;
    await cap.start((f) => {
      bytes += f.length;
      nonZero += f.filter((b) => b !== 0).length;
    });
    expect(cap.running).toBe(true);
    jest.advanceTimersByTime(3000);
    expect(bytes).toBe(3 * BYTES_PER_SECOND);
    expect(nonZero).toBe(0);
  });

  it('stops cleanly and is safe to start twice', async () => {
    const cap = new SimulatedCapture();
    const frames: number[] = [];
    await cap.start((f) => frames.push(f.length));
    await cap.start((f) => frames.push(f.length));
    jest.advanceTimersByTime(1000);
    const before = frames.length;
    await cap.stop();
    jest.advanceTimersByTime(1000);
    expect(frames.length).toBe(before);
    expect(cap.running).toBe(false);
  });
});

function fakeBackend(opts: { permission?: boolean } = {}) {
  const calls: string[] = [];
  let onChunk: (b64: string) => void = () => undefined;
  let onInterrupt: (reason: string) => void = () => undefined;
  const backend: MicBackend = {
    requestPermission: async () => opts.permission ?? true,
    start: async (c, i) => {
      calls.push('start');
      onChunk = c;
      onInterrupt = i;
    },
    stop: async () => {
      calls.push('stop');
    },
  };
  return { backend, calls, chunk: (b: string) => onChunk(b), interrupt: (r: string) => onInterrupt(r) };
}

const b64 = (bytes: number[]) => Buffer.from(bytes).toString('base64');

describe('base64ToBytes', () => {
  it('matches Buffer for every padding length and arbitrary bytes', () => {
    for (const n of [0, 1, 2, 3, 4, 5, 31, 32000]) {
      const bytes = Array.from({ length: n }, (_, i) => (i * 37 + 11) % 256);
      expect(Array.from(base64ToBytes(b64(bytes)))).toEqual(bytes);
    }
  });
  it('rejects data that is not base64', () => {
    expect(() => base64ToBytes('@@@@')).toThrow();
  });
});

describe('MicrophoneCapture', () => {
  it('does nothing without the microphone permission', async () => {
    const f = fakeBackend({ permission: false });
    const cap = new MicrophoneCapture(f.backend);
    await expect(cap.start(() => undefined)).rejects.toBeInstanceOf(CaptureUnavailableError);
    expect(f.calls).toEqual([]);
    expect(cap.running).toBe(false);
  });

  it('delivers decoded PCM frames and ignores late chunks after stop', async () => {
    const f = fakeBackend();
    const cap = new MicrophoneCapture(f.backend);
    const got: number[][] = [];
    await cap.start((fr) => got.push(Array.from(fr)));
    f.chunk(b64([1, 2, 3, 4]));
    f.chunk('');
    expect(got).toEqual([[1, 2, 3, 4]]);
    await cap.stop();
    f.chunk(b64([9, 9]));
    expect(got).toHaveLength(1);
    expect(f.calls).toEqual(['start', 'stop']);
    expect(cap.running).toBe(false);
  });

  it('skips a corrupt chunk instead of crashing the stream', async () => {
    const f = fakeBackend();
    const cap = new MicrophoneCapture(f.backend);
    const got: number[][] = [];
    await cap.start((fr) => got.push(Array.from(fr)));
    f.chunk('@@@@');
    f.chunk(b64([5, 6]));
    expect(got).toEqual([[5, 6]]);
  });

  it('reports at once when the OS takes the microphone, and still releases the recorder', async () => {
    const f = fakeBackend();
    const cap = new MicrophoneCapture(f.backend);
    const reasons: string[] = [];
    await cap.start(() => undefined, (r) => reasons.push(r));
    f.interrupt('phoneCall');
    expect(cap.running).toBe(false); // the indicator must not say recording
    expect(reasons).toEqual(['phoneCall']);
    await cap.stop();
    expect(f.calls).toEqual(['start', 'stop']); // the native recorder is closed
  });

  it('ignores interruptions that do not take the microphone away', async () => {
    const f = fakeBackend();
    const cap = new MicrophoneCapture(f.backend);
    const reasons: string[] = [];
    await cap.start(() => undefined, (r) => reasons.push(r));
    f.interrupt('audioFocusGain');
    expect(cap.running).toBe(true);
    expect(reasons).toEqual([]);
  });

  it('is safe to start twice and to stop when never started', async () => {
    const f = fakeBackend();
    const cap = new MicrophoneCapture(f.backend);
    await new MicrophoneCapture(fakeBackend().backend).stop();
    await cap.start(() => undefined);
    await cap.start(() => undefined);
    expect(f.calls).toEqual(['start']);
  });

  it('without the native module (Expo Go, web, tests) it refuses with an explanation', async () => {
    await expect(new MicrophoneCapture().start(() => undefined)).rejects.toBeInstanceOf(CaptureUnavailableError);
  });
});

describe('what the recorder is configured to do', () => {
  it('streams 16 kHz mono PCM16 and never keeps audio on the phone', () => {
    expect(MIC_CONFIG).toMatchObject({ sampleRate: 16000, channels: 1, encoding: 'pcm_16bit' });
    expect(MIC_CONFIG.output.primary.enabled).toBe(false);
    expect(MIC_CONFIG.output.compressed.enabled).toBe(false);
    expect(MIC_CONFIG.showNotification).toBe(false);
  });

  it('declares only the permissions it needs in app.json', () => {
    const app = require('../../../../app.json');
    const plugin = app.expo.plugins.find((p: unknown) => Array.isArray(p) && p[0] === '@siteed/audio-studio');
    expect(plugin[1]).toMatchObject({
      enablePhoneStateHandling: false,
      enableNotifications: false,
      enableBackgroundAudio: false,
      enableDeviceDetection: false,
    });
  });
});

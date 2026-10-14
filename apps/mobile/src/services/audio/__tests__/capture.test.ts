import { BYTES_PER_SECOND, CaptureUnavailableError, MicrophoneCapture, SimulatedCapture } from '../capture';

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

describe('MicrophoneCapture', () => {
  it('refuses to pretend: no native streaming module is installed', async () => {
    const cap = new MicrophoneCapture();
    await expect(cap.start()).rejects.toBeInstanceOf(CaptureUnavailableError);
    expect(cap.running).toBe(false);
  });
});

import type { PurposeStatus, Segment } from '@/api/schemas';

import {
  CONSENT_GROUPS,
  describeClose,
  formatClock,
  LOW_CONFIDENCE,
  mergeSegments,
  missingForRecording,
  needsCheck,
  shownText,
  PURPOSE_LABELS,
  recordingIndicator,
} from '../recording';

const seg = (seq: number, text = 'x', confidence: number | null = 0.9): Segment => ({
  id: String(seq), seq, speaker_id: 'spk_0', speaker_role: 'UNKNOWN', start_ms: 0, end_ms: 1, raw_text: text,
  normalised_text: null, language: 'en-IN', secondary_language: null, confidence, code_switch_spans: [],
});

describe('recordingIndicator never claims more than is true', () => {
  it('says RECORDING only when live, capturing and connected', () => {
    expect(recordingIndicator({ phase: 'live', capturing: true, connected: true })).toMatchObject({ label: 'RECORDING', isRecording: true });
  });
  it.each([
    { phase: 'live', capturing: true, connected: false },
    { phase: 'live', capturing: false, connected: true },
    { phase: 'paused', capturing: true, connected: true },
    { phase: 'ended', capturing: true, connected: true },
    { phase: 'starting', capturing: true, connected: true },
    { phase: 'error', capturing: true, connected: true },
    { phase: 'idle', capturing: false, connected: false },
  ] as const)('is NOT recording for %j', (s) => {
    expect(recordingIndicator(s).isRecording).toBe(false);
  });
  it('makes a lost connection obvious', () => {
    expect(recordingIndicator({ phase: 'live', capturing: true, connected: false }).label).toContain('NOT RECORDING');
  });
});

describe('describeClose', () => {
  it('explains consent withdrawal specifically', () => {
    expect(describeClose(4001, 'CONSENT_WITHDRAWN')).toMatch(/withdrew consent/);
    expect(describeClose(4001, 'USER')).toMatch(/ended/);
  });
  it('offers a way forward for service failures', () => {
    expect(describeClose(4503)).toMatch(/manually/);
    expect(describeClose(1011)).toMatch(/manually/);
    expect(describeClose(1006)).toMatch(/paused/);
  });
});

describe('transcript helpers', () => {
  it('flags only lines the recogniser was unsure about', () => {
    expect(needsCheck(seg(1, 'x', LOW_CONFIDENCE - 0.01))).toBe(true);
    expect(needsCheck(seg(1, 'x', LOW_CONFIDENCE))).toBe(false);
    expect(needsCheck(seg(1, 'x', null))).toBe(false); // no score means no claim either way
    // Unsure which language was spoken (seen live: 0.498 and 0.663 on a short, mixed-language phrase).
    expect(needsCheck({ ...seg(1, 'x', null), language_confidence: 0.498 })).toBe(true);
    expect(needsCheck({ ...seg(1, 'x', null), language_confidence: 0.98 })).toBe(false);
  });
  it('merges polled segments by sequence without duplicates', () => {
    const merged = mergeSegments([seg(1), seg(2)], [seg(2, 'updated'), seg(3)]);
    expect(merged.map((s) => s.seq)).toEqual([1, 2, 3]);
    expect(merged[1].raw_text).toBe('updated');
    const same = [seg(1)];
    expect(mergeSegments(same, [])).toBe(same);
  });
  it('formats a clock', () => {
    expect(formatClock(0)).toBe('00:00');
    expect(formatClock(125.9)).toBe('02:05');
    expect(formatClock(-3)).toBe('00:00');
  });
});

describe('consent helpers', () => {
  const status = (purpose: string, active: boolean): PurposeStatus => ({
    purpose, active, consent_id: null, policy_version: null, granted_by_type: null, blocked_by: null, wording_available: true,
  });
  it('names exactly what is still missing', () => {
    const s = [status('AUDIO_RECORDING', true), status('SPEECH_TRANSCRIPTION', false), status('AI_PROCESSING', false)];
    expect(missingForRecording(s, false)).toEqual(['SPEECH_TRANSCRIPTION']);
    expect(missingForRecording(s, true)).toEqual(['SPEECH_TRANSCRIPTION', 'AI_PROCESSING']);
  });
  it('shows every purpose in some group, none twice, each with a label', () => {
    const all = CONSENT_GROUPS.flatMap((g) => g.purposes);
    expect(new Set(all).size).toBe(all.length);
    expect(all).toHaveLength(8);
    all.forEach((p) => expect(PURPOSE_LABELS[p]).toBeTruthy());
  });
  it('keeps optional extras separate from recording consent', () => {
    const recording = CONSENT_GROUPS.find((g) => g.title === 'Recording this visit');
    const extras = CONSENT_GROUPS.find((g) => g.title === 'Optional extras');
    expect(recording?.purposes).not.toContain('AI_MODEL_IMPROVEMENT');
    expect(extras?.purposes).toContain('AI_MODEL_IMPROVEMENT');
  });
});

import { describeInterruption } from '../recording';

describe('describeInterruption', () => {
  it('says plainly why recording stopped', () => {
    expect(describeInterruption('phoneCall')).toMatch(/phone call/);
    expect(describeInterruption('something-new')).toMatch(/Nothing is being recorded/);
  });
});

describe('shownText', () => {
  it('prefers a staff correction and otherwise shows what was heard', () => {
    expect(shownText({ raw_text: 'fewer', corrected_text: 'fever' })).toBe('fever');
    expect(shownText({ raw_text: 'fewer', corrected_text: null })).toBe('fewer');
    expect(shownText({ raw_text: 'fewer' })).toBe('fewer');
  });
});

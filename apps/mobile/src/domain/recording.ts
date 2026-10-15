import type { PurposeStatus, Segment } from '@/api/schemas';

import type { Tone } from './clinical';

export type Phase = 'idle' | 'starting' | 'live' | 'paused' | 'ended' | 'error';

/**
 * What the recording indicator may say. "Recording" requires ALL of: the session is live, the
 * microphone is running, and the connection to the server is open. If any one is missing the
 * screen must not claim that audio is being captured.
 */
export function recordingIndicator(s: { phase: Phase; capturing: boolean; connected: boolean }): {
  label: string;
  tone: Tone;
  isRecording: boolean;
} {
  if (s.phase === 'live' && s.capturing && s.connected) return { label: 'RECORDING', tone: 'danger', isRecording: true };
  if (s.phase === 'live') return { label: 'CONNECTION LOST — NOT RECORDING', tone: 'warning', isRecording: false };
  if (s.phase === 'starting') return { label: 'Starting…', tone: 'neutral', isRecording: false };
  if (s.phase === 'paused') return { label: 'PAUSED — NOT RECORDING', tone: 'warning', isRecording: false };
  if (s.phase === 'ended') return { label: 'Recording ended', tone: 'neutral', isRecording: false };
  return { label: 'Not recording', tone: 'neutral', isRecording: false };
}

export function describeClose(code: number, reason = ''): string {
  switch (code) {
    case 4001:
      return reason === 'CONSENT_WITHDRAWN'
        ? 'The patient withdrew consent. Recording has stopped.'
        : 'The recording was ended.';
    case 4002:
      return 'The time limit for one recording was reached. You can resume.';
    case 4401:
      return 'You need to sign in again.';
    case 4403:
      return 'Recording is not allowed right now (consent or permission missing).';
    case 4404:
      return 'This recording session was not found.';
    case 4409:
      return 'This recording is not active, or is already open on another device.';
    case 4503:
      return 'The speech service is not available. Continue by documenting manually.';
    case 1011:
      return 'The speech service failed. Recording is paused; you can try again or document manually.';
    default:
      return 'The connection was lost. Recording is paused.';
  }
}

export const ROLE_LABELS: Record<string, string> = {
  DOCTOR: 'Doctor',
  PATIENT: 'Patient',
  FAMILY_MEMBER: 'Family member',
  OTHER_STAFF: 'Other staff',
  UNKNOWN: 'Who is this?',
};
export const ROLE_OPTIONS = ['DOCTOR', 'PATIENT', 'FAMILY_MEMBER', 'OTHER_STAFF', 'UNKNOWN'] as const;

/** Below this the recogniser itself was unsure; flag the line so a person checks it. */
export const LOW_CONFIDENCE = 0.75;
export const needsCheck = (s: Pick<Segment, 'confidence'>): boolean =>
  s.confidence !== null && s.confidence < LOW_CONFIDENCE;

export const formatClock = (totalSeconds: number): string => {
  const s = Math.max(0, Math.floor(totalSeconds));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
};

/** Merge newly polled segments into the ones we already hold, by sequence number. */
export function mergeSegments(current: Segment[], incoming: Segment[]): Segment[] {
  if (incoming.length === 0) return current;
  const bySeq = new Map(current.map((s) => [s.seq, s]));
  for (const s of incoming) bySeq.set(s.seq, s);
  return [...bySeq.values()].sort((a, b) => a.seq - b.seq);
}

export const CONSENT_GROUPS: { title: string; hint: string; purposes: string[] }[] = [
  { title: 'Care', hint: 'Needed to treat the patient.', purposes: ['MEDICAL_CARE'] },
  { title: 'Recording this visit', hint: 'Both are needed before any recording starts.', purposes: ['AUDIO_RECORDING', 'SPEECH_TRANSCRIPTION'] },
  { title: 'Computer assistance', hint: 'Lets software suggest notes. The doctor decides everything.', purposes: ['AI_PROCESSING'] },
  { title: 'Keeping the audio', hint: 'Without this the audio is deleted as soon as it is turned into text.', purposes: ['AUDIO_RETENTION'] },
  { title: 'Optional extras', hint: 'Saying no never affects care.', purposes: ['RESEARCH', 'ANALYTICS', 'AI_MODEL_IMPROVEMENT'] },
];

export const PURPOSE_LABELS: Record<string, string> = {
  MEDICAL_CARE: 'Medical care',
  AUDIO_RECORDING: 'Record the conversation',
  SPEECH_TRANSCRIPTION: 'Turn speech into text',
  AI_PROCESSING: 'Computer-assisted notes',
  AUDIO_RETENTION: 'Keep the audio for a limited time',
  RESEARCH: 'Research',
  ANALYTICS: 'Clinic analytics',
  AI_MODEL_IMPROVEMENT: 'Improve the software',
};

/** Consents still missing for a recording, so the app can say exactly what to ask the patient. */
export function missingForRecording(status: PurposeStatus[], ai: boolean): string[] {
  const need = ['AUDIO_RECORDING', 'SPEECH_TRANSCRIPTION', ...(ai ? ['AI_PROCESSING'] : [])];
  return need.filter((p) => !status.find((s) => s.purpose === p)?.active);
}

/** Plain-language reason the microphone was taken, shown when a recording pauses itself. */
export function describeInterruption(reason: string): string {
  switch (reason) {
    case 'phoneCall':
      return 'Recording paused: a phone call used the microphone. Resume when the call ends.';
    case 'audioFocusLoss':
      return 'Recording paused: another app took the microphone. Resume when it is free.';
    case 'deviceDisconnected':
      return 'Recording paused: the microphone was disconnected.';
    default:
      return 'Recording paused: the microphone stopped. Nothing is being recorded.';
  }
}

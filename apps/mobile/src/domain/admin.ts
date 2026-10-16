import type { KnowledgeDoc, OrgPolicy, StaffUser } from '@/api/schemas';

/** Switches depend on each other on the server too; the screen applies the same rules up front. */
export function togglePolicy(p: OrgPolicy, key: keyof OrgPolicy, value: boolean): OrgPolicy {
  const next = { ...p, [key]: value } as OrgPolicy;
  if (key === 'recording_enabled' && !value) {
    next.audio_retention = 'DISCARD_AFTER_TRANSCRIPTION'; // nothing to retain without recording
  }
  if (key === 'ai_processing_enabled' && !value) {
    next.ai_suggestions_enabled = false; // suggestions sit on top of AI processing
  }
  return next;
}

export function policyProblem(p: OrgPolicy): string | null {
  if (p.audio_retention === 'RETAIN_DAYS' && !p.recording_enabled) return 'Audio cannot be kept when recording is off.';
  if (p.ai_suggestions_enabled && !p.ai_processing_enabled) return 'Suggestions need AI processing to be on.';
  if (p.retain_days < 1 || p.retain_days > 3650) return 'Keep audio for between 1 and 3650 days.';
  return null;
}

/** What each switch means in plain words, so an administrator knows what they are enabling. */
export const POLICY_HELP: Record<string, string> = {
  recording_enabled: 'Doctors and nurses may record consultations (each patient still has to consent).',
  ai_processing_enabled: 'Software may read transcripts and charts to suggest notes (each patient needs separate AI consent).',
  ai_suggestions_enabled: 'Software may also suggest things to consider. Doctors still decide.',
  ai_suggestions_require_source: 'Drop clinical suggestions that do not cite an approved reference document.',
};

export const passwordProblem = (pw: string): string | null =>
  pw.length < 12 ? 'Use at least 12 characters.' : null;

export const emailProblem = (e: string): string | null => (/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e.trim()) ? null : 'Enter a valid email address.');

/** Reference passages: one per block, separated by a blank line. */
export function splitPassages(text: string): string[] {
  return text
    .split(/\n\s*\n/)
    .map((p) => p.replace(/\s+/g, ' ').trim())
    .filter((p) => p.length > 0)
    .slice(0, 500);
}

/** The approver must be someone other than whoever added the document. */
export function approvalState(doc: KnowledgeDoc, meId: string): 'approved' | 'retired' | 'own' | 'ready' {
  if (doc.retired_at) return 'retired';
  if (doc.approved) return 'approved';
  return doc.created_by === meId ? 'own' : 'ready';
}

const TIME = /^([01]\d|2[0-3]):[0-5]\d$/;
export const timeProblem = (start: string, end: string): string | null => {
  if (!TIME.test(start) || !TIME.test(end)) return 'Write times as 24-hour HH:MM, for example 09:00.';
  return start < end ? null : 'The start time must be before the end time.';
};

export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export const hoursFor = (days: number[], start: string, end: string) =>
  [...days].sort((a, b) => a - b).map((weekday) => ({ weekday, start_time: `${start}:00`, end_time: `${end}:00` }));

/** "Mon-Fri 09:00-17:00" style summary of a practitioner's hours. */
export function describeHours(hours: { weekday: number; start_time: string; end_time: string }[]): string {
  if (hours.length === 0) return 'No working hours set (cannot be booked)';
  return [...hours]
    .sort((a, b) => a.weekday - b.weekday)
    .map((h) => `${WEEKDAYS[h.weekday]} ${h.start_time.slice(0, 5)}-${h.end_time.slice(0, 5)}`)
    .join(', ');
}

export const isDoctorUser = (u: StaffUser): boolean => u.roles.includes('doctor');

/** Plain English for an audit action code, falling back to the code itself. */
export function describeAction(action: string): string {
  return action.toLowerCase().replace(/_/g, ' ');
}

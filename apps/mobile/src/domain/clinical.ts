import type { Observation } from '@/api/schemas';

export type Tone = 'neutral' | 'success' | 'warning' | 'danger' | 'ai';

export const VITAL_LABELS: Record<string, string> = {
  TEMPERATURE_C: 'Temperature',
  HEART_RATE: 'Heart rate',
  RESPIRATORY_RATE: 'Resp. rate',
  SPO2: 'SpO₂',
  SYSTOLIC_BP: 'Systolic BP',
  DIASTOLIC_BP: 'Diastolic BP',
  HEIGHT_CM: 'Height',
  WEIGHT_KG: 'Weight',
  BLOOD_GLUCOSE: 'Glucose',
  PAIN_SCORE: 'Pain',
};

export const interpretationTone = (i: string): Tone => {
  if (i.startsWith('CRITICAL')) return 'danger';
  if (i === 'LOW' || i === 'HIGH') return 'warning';
  if (i === 'NORMAL') return 'success';
  return 'neutral';
};

export const interpretationLabel = (i: string): string | null => {
  if (i === 'NORMAL') return 'Normal';
  if (i === 'LOW') return 'Low';
  if (i === 'HIGH') return 'High';
  if (i === 'CRITICAL_LOW') return 'Critically low';
  if (i === 'CRITICAL_HIGH') return 'Critically high';
  return null; // UNKNOWN / NOT_APPLICABLE: say nothing rather than imply normal
};

const SOURCE_LABELS: Record<string, string> = {
  PATIENT_REPORTED: 'Patient said',
  STAFF_ENTERED: 'Staff',
  DOCTOR_ENTERED: 'Doctor',
  DEVICE_RECORDED: 'Device',
  LAB_RESULT: 'Lab',
  EXTERNAL_RECORD: 'External record',
  AI_EXTRACTED: 'AI',
};

/** One short phrase + tone saying where a fact came from and whether a clinician has checked it. */
export function provenance(source: string, verification: string): { text: string; tone: Tone } {
  const from = SOURCE_LABELS[source] ?? source;
  switch (verification) {
    case 'CLINICIAN_CONFIRMED':
      return { text: `${from} · confirmed`, tone: 'success' };
    case 'CLINICIAN_EDITED':
      return { text: `${from} · corrected`, tone: 'success' };
    case 'CLINICIAN_REJECTED':
      return { text: `${from} · rejected`, tone: 'danger' };
    case 'AI_GENERATED':
    case 'REQUIRES_REVIEW':
      return { text: `${from} · needs review`, tone: source === 'AI_EXTRACTED' ? 'ai' : 'warning' };
    default:
      return { text: `${from} · unverified`, tone: 'warning' };
  }
}

export const needsVerification = (verification: string): boolean =>
  ['UNVERIFIED', 'AI_GENERATED', 'REQUIRES_REVIEW'].includes(verification);

export function formatVital(o: Pick<Observation, 'value' | 'unit' | 'original_value' | 'original_unit'>): string {
  const shown = `${Number(o.value.toFixed(1))} ${o.unit}`;
  return o.original_value != null ? `${shown} (entered ${o.original_value} ${o.original_unit ?? ''})` : shown;
}

/** Blank → undefined; otherwise a finite number or NaN so forms can flag bad input. */
export function parseNumber(text: string | undefined): number | undefined {
  const t = (text ?? '').trim();
  if (t === '') return undefined;
  const n = Number(t);
  return Number.isFinite(n) ? n : Number.NaN;
}

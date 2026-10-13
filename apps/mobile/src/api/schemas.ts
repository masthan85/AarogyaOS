import { z } from 'zod';

export const tokenPairSchema = z.object({
  access_token: z.string(),
  refresh_token: z.string(),
  token_type: z.string(),
  expires_in: z.number(),
});

export const meSchema = z.object({
  id: z.string(),
  organisation_id: z.string().nullable(),
  email: z.string(),
  full_name: z.string(),
  roles: z.array(z.string()),
  permissions: z.array(z.string()),
});

export const facilitySchema = z.object({
  id: z.string(),
  name: z.string(),
  code: z.string(),
  kind: z.string(),
  address: z.string().nullable(),
  timezone: z.string(),
  status: z.string(),
});

export const organisationSchema = z.object({
  id: z.string(),
  name: z.string(),
  slug: z.string(),
  status: z.string(),
});

export type Me = z.infer<typeof meSchema>;
export type Facility = z.infer<typeof facilitySchema>;
export type Organisation = z.infer<typeof organisationSchema>;

// ---- Phase 2 -------------------------------------------------------------------

export const patientHitSchema = z.object({
  id: z.string(),
  mrn: z.string(),
  full_name: z.string(),
  age_years: z.number().nullable(),
  administrative_gender: z.string(),
  mobile_masked: z.string().nullable(),
});

export const duplicateCandidateSchema = patientHitSchema.extend({ reasons: z.array(z.string()) });

export const patientSchema = z.object({
  id: z.string(),
  mrn: z.string(),
  full_name: z.string(),
  date_of_birth: z.string().nullable(),
  dob_is_estimated: z.boolean(),
  age_years: z.number().nullable(),
  administrative_gender: z.string(),
  mobile: z.string().nullable(),
  address: z.string().nullable(),
  emergency_contact_name: z.string().nullable(),
  emergency_contact_phone: z.string().nullable(),
  preferred_language: z.string(),
  spoken_languages: z.array(z.string()),
  identifiers: z.array(
    z.object({ id: z.string(), system: z.string(), masked: z.string(), verified: z.boolean() }),
  ),
  version: z.number(),
});

export const timelineEventSchema = z.object({
  id: z.string(),
  event_type: z.string(),
  aggregate_type: z.string(),
  occurred_at: z.string(),
});

export const practitionerSchema = z.object({
  id: z.string(),
  full_name: z.string(),
  facility_id: z.string(),
  specialty: z.string(),
  consultation_minutes: z.number(),
});

export const slotSchema = z.object({ start_at: z.string(), end_at: z.string() });

export const appointmentSchema = z.object({
  id: z.string(),
  patient_id: z.string(),
  patient_name: z.string(),
  patient_mrn: z.string(),
  practitioner_id: z.string().nullable(),
  practitioner_name: z.string().nullable(),
  facility_id: z.string(),
  kind: z.string(),
  status: z.string(),
  start_at: z.string(),
  end_at: z.string(),
  reason: z.string().nullable(),
  token_number: z.number().nullable(),
  priority: z.string().nullable(),
});

export const queueItemSchema = z.object({
  appointment_id: z.string(),
  token_number: z.number(),
  priority: z.string(),
  status: z.string(),
  patient_id: z.string(),
  patient_name: z.string(),
  patient_mrn: z.string(),
  age_years: z.number().nullable(),
  administrative_gender: z.string(),
  practitioner_id: z.string().nullable(),
  practitioner_name: z.string().nullable(),
  waiting_since: z.string(),
  encounter_status: z.string().nullable(),
});

export type PatientHit = z.infer<typeof patientHitSchema>;
export type DuplicateCandidate = z.infer<typeof duplicateCandidateSchema>;
export type Patient = z.infer<typeof patientSchema>;
export type TimelineEvent = z.infer<typeof timelineEventSchema>;
export type Practitioner = z.infer<typeof practitionerSchema>;
export type Slot = z.infer<typeof slotSchema>;
export type Appointment = z.infer<typeof appointmentSchema>;
export type QueueItem = z.infer<typeof queueItemSchema>;

// ---- Phase 3: clinical record -----------------------------------------------------

const fact = {
  id: z.string(),
  source: z.string(),
  verification_state: z.string(),
  is_current: z.boolean(),
};

export const encounterSchema = z.object({
  id: z.string(),
  patient_id: z.string(),
  appointment_id: z.string(),
  practitioner_id: z.string().nullable(),
  status: z.string(),
  triage_category: z.string().nullable(),
});

export const observationSchema = z.object({
  ...fact,
  code: z.string(),
  value: z.coerce.number(),
  unit: z.string(),
  original_value: z.coerce.number().nullable(),
  original_unit: z.string().nullable(),
  interpretation: z.string(),
  observed_at: z.string(),
});

export const noteSchema = z.object({ ...fact, note_type: z.string(), content: z.string() });
export const conditionSchema = z.object({
  ...fact,
  display: z.string(),
  certainty: z.string(),
  clinical_status: z.string(),
  category: z.string(),
});
export const allergySchema = z.object({
  ...fact,
  substance: z.string(),
  severity: z.string(),
  certainty: z.string(),
  reaction: z.string().nullable(),
  is_nka: z.boolean(),
});
export const medicationSchema = z.object({
  ...fact,
  name: z.string(),
  dose: z.string().nullable(),
  frequency: z.string().nullable(),
  status: z.string(),
});

export const resultSchema = z.object({
  id: z.string(),
  test_name: z.string(),
  value_numeric: z.coerce.number().nullable(),
  value_text: z.string().nullable(),
  unit: z.string().nullable(),
  interpretation: z.string(),
  reviewed_at: z.string().nullable(),
});

export const alertSchema = z.object({
  level: z.enum(['CRITICAL', 'WARNING', 'INFO']),
  code: z.string(),
  message: z.string(),
});

export const clinicalStateSchema = z.object({
  allergies: z.array(allergySchema),
  allergy_status_recorded: z.boolean(),
  conditions: z.array(conditionSchema),
  medications: z.array(medicationSchema),
  latest_vitals: z.array(observationSchema),
  bmi: z.number().nullable(),
  results_awaiting_review: z.array(resultSchema),
  alerts: z.array(alertSchema),
});

export const prescriptionItemSchema = z.object({
  id: z.string(),
  position: z.number(),
  medicine_name: z.string(),
  strength: z.string().nullable(),
  dose: z.string(),
  route: z.string(),
  frequency: z.string(),
  duration_days: z.number().nullable(),
});
export const prescriptionSchema = z.object({
  id: z.string(),
  status: z.string(),
  items: z.array(prescriptionItemSchema),
});
export const orderSchema = z.object({
  id: z.string(),
  category: z.string(),
  name: z.string(),
  priority: z.string(),
  status: z.string(),
});
export const followUpSchema = z.object({
  id: z.string(),
  due_date: z.string(),
  reason: z.string(),
  status: z.string(),
});

export const encounterDetailSchema = z.object({
  encounter: encounterSchema,
  notes: z.array(noteSchema),
  vitals: z.array(observationSchema),
  conditions: z.array(conditionSchema),
  prescriptions: z.array(prescriptionSchema),
  orders: z.array(orderSchema),
  follow_ups: z.array(followUpSchema),
});

export const safetyWarningSchema = z.object({
  code: z.string(),
  level: z.enum(['WARNING', 'INFO']),
  message: z.string(),
});
export const safetyCheckSchema = z.object({
  warnings: z.array(safetyWarningSchema),
  checks_not_performed: z.array(z.string()),
});

export type Encounter = z.infer<typeof encounterSchema>;
export type Observation = z.infer<typeof observationSchema>;
export type ClinicalState = z.infer<typeof clinicalStateSchema>;
export type EncounterDetail = z.infer<typeof encounterDetailSchema>;
export type Prescription = z.infer<typeof prescriptionSchema>;
export type SafetyWarning = z.infer<typeof safetyWarningSchema>;
export type ClinicalAlert = z.infer<typeof alertSchema>;

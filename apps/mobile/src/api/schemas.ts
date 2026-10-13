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
});

export type PatientHit = z.infer<typeof patientHitSchema>;
export type DuplicateCandidate = z.infer<typeof duplicateCandidateSchema>;
export type Patient = z.infer<typeof patientSchema>;
export type TimelineEvent = z.infer<typeof timelineEventSchema>;
export type Practitioner = z.infer<typeof practitionerSchema>;
export type Slot = z.infer<typeof slotSchema>;
export type Appointment = z.infer<typeof appointmentSchema>;
export type QueueItem = z.infer<typeof queueItemSchema>;

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
  facility_id: z.string(),
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
  instructions: z.string().nullable().optional(),
});
export const prescriptionSchema = z.object({
  id: z.string(),
  status: z.string(),
  signed_at: z.string().nullable().optional(),
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

// ---- Phase 4: consent, recording, transcripts -----------------------------------------

export const languageSchema = z.object({
  tag: z.string(),
  name: z.string(),
  native_name: z.string(),
  script: z.string(),
});
export type Language = z.infer<typeof languageSchema>;

export const purposeStatusSchema = z.object({
  purpose: z.string(),
  active: z.boolean(),
  consent_id: z.string().nullable(),
  policy_version: z.number().nullable(),
  granted_by_type: z.string().nullable(),
  blocked_by: z.string().nullable(),
  wording_available: z.boolean(),
});
export const consentSchema = z.object({
  id: z.string(),
  purpose: z.string(),
  status: z.string(),
  granted_by_type: z.string(),
  representative_name: z.string().nullable(),
});
export const patientConsentsSchema = z.object({
  status: z.array(purposeStatusSchema),
  history: z.array(consentSchema),
  guardian_required: z.boolean(),
});
export const policySchema = z.object({
  id: z.string(),
  purpose: z.string(),
  language: z.string(),
  version: z.number(),
  title: z.string(),
  body: z.string(),
  legally_reviewed: z.boolean(),
});
export type PurposeStatus = z.infer<typeof purposeStatusSchema>;
export type PatientConsents = z.infer<typeof patientConsentsSchema>;
export type ConsentPolicy = z.infer<typeof policySchema>;

export const interactionSchema = z.object({
  id: z.string(),
  patient_id: z.string(),
  encounter_id: z.string().nullable(),
  purpose: z.string(),
  status: z.enum(['CREATED', 'ACTIVE', 'PAUSED', 'ENDED']),
  ai_processing: z.boolean(),
  speech_provider: z.string(),
  is_development: z.boolean(),
  language_hint: z.string(),
  end_reason: z.string().nullable(),
  pause_reason: z.string().nullable(),
  audio_seconds: z.number(),
});
export const startInfoSchema = z.object({
  interaction: interactionSchema,
  gateway_path: z.string(),
  audio_format: z.object({ encoding: z.string(), sample_rate: z.number(), channels: z.number(), max_frame_bytes: z.number() }),
});
export const segmentSchema = z.object({
  id: z.string(),
  seq: z.number(),
  speaker_id: z.string().nullable(),
  speaker_role: z.string(),
  start_ms: z.number(),
  end_ms: z.number(),
  raw_text: z.string(),
  normalised_text: z.string().nullable(),
  language: z.string().nullable(),
  secondary_language: z.string().nullable(),
  language_confidence: z.number().nullable().optional(),
  confidence: z.number().nullable(),
  code_switch_spans: z.array(z.object({ start: z.number(), end: z.number(), language: z.string() })),
});
export const transcriptSchema = z.object({
  interaction_id: z.string(),
  status: z.string(),
  is_development: z.boolean(),
  segments: z.array(segmentSchema),
  speakers: z.array(z.object({ speaker_id: z.string(), role: z.string(), label: z.string().nullable() })),
  partial: z.object({ text: z.string(), speaker_id: z.string().nullable(), language: z.string().nullable() }).nullable(),
  last_seq: z.number(),
});
export type Interaction = z.infer<typeof interactionSchema>;
export type StartInfo = z.infer<typeof startInfoSchema>;
export type Segment = z.infer<typeof segmentSchema>;
export type Transcript = z.infer<typeof transcriptSchema>;

// ---- Phase 5: AI-assisted documentation and decision support -----------------------------

export const analyseSchema = z.object({
  status: z.enum(['OK', 'FAILED', 'NOTHING_NEW']),
  extraction_id: z.string().nullable().optional(),
  new_candidates: z.number(),
  dropped: z.record(z.string(), z.number()),
  message: z.string().nullable().optional(),
  is_development: z.boolean(),
});
export const candidateSchema = z.object({
  id: z.string(),
  interaction_id: z.string(),
  encounter_id: z.string().nullable(),
  kind: z.string(),
  text: z.string(),
  assertion: z.string(),
  subject: z.string(),
  attributes: z.record(z.string(), z.string()),
  original_term: z.string().nullable(),
  evidence: z.array(z.object({ segment_id: z.string(), seq: z.number(), quote: z.string(), speaker_role: z.string() })),
  risk_flags: z.array(z.string()),
  status: z.string(),
  edited_text: z.string().nullable(),
  result_kind: z.string().nullable(),
  created_at: z.string(),
});
export const suggestionSchema = z.object({
  id: z.string(),
  encounter_id: z.string(),
  category: z.string(),
  title: z.string(),
  explanation: z.string(),
  uncertainty: z.string(),
  uncertainty_note: z.string().nullable(),
  supporting_context: z.array(z.record(z.string(), z.string())),
  evidence_sources: z.array(z.record(z.string(), z.string())),
  payload: z.record(z.string(), z.string()),
  warnings: z.array(z.string()),
  origin: z.string(),
  provider: z.string().nullable(),
  model: z.string().nullable(),
  status: z.string(),
  created_at: z.string(),
});
export const reviewBundleSchema = z.object({
  candidates: z.array(candidateSchema),
  suggestions: z.array(suggestionSchema),
  ai_enabled: z.boolean(),
  suggestions_enabled: z.boolean(),
});
export const reviewResultSchema = z.object({
  candidate: candidateSchema,
  result_kind: z.string().nullable(),
  result_id: z.string().nullable(),
});
export const generateSchema = z.object({
  created: z.number(),
  dropped: z.record(z.string(), z.number()),
  model_used: z.boolean(),
  message: z.string().nullable().optional(),
});
export const suggestionActionSchema = z.object({
  suggestion: suggestionSchema,
  result_kind: z.string().nullable().optional(),
  result_id: z.string().nullable().optional(),
});
export type Analyse = z.infer<typeof analyseSchema>;
export type Candidate = z.infer<typeof candidateSchema>;
export type Suggestion = z.infer<typeof suggestionSchema>;
export type ReviewBundle = z.infer<typeof reviewBundleSchema>;

// ---- Note templates, documents (summaries and referral letters), chart questions --------------

export const templateSchema = z.object({
  id: z.string(),
  name: z.string(),
  specialty: z.string().nullable(),
  sections: z.array(z.object({ note_type: z.string(), title: z.string(), hint: z.string() })),
  active: z.boolean(),
  builtin: z.boolean(),
});
export const documentSchema = z.object({
  id: z.string(),
  encounter_id: z.string(),
  kind: z.string(),
  recipient: z.string().nullable(),
  version: z.number(),
  language: z.string(),
  content: z.string(),
  source_content: z.string(),
  translation_status: z.string(),
  status: z.string(),
  approved_at: z.string().nullable(),
  created_at: z.string(),
});
export const askSchema = z.object({
  answer: z
    .array(
      z.object({
        text: z.string(),
        citations: z.array(z.object({ ref: z.string(), label: z.string(), date: z.string().nullable().optional() })),
      }),
    )
    .nullable(),
  answered: z.boolean(),
  matches: z.array(z.object({ ref: z.string(), text: z.string(), date: z.string().nullable().optional() })),
  used_ai: z.boolean(),
  message: z.string().nullable().optional(),
  is_development: z.boolean(),
});
export type NoteTemplate = z.infer<typeof templateSchema>;
export type ClinicalDocument = z.infer<typeof documentSchema>;
export type AskResult = z.infer<typeof askSchema>;

// ---- Administration ------------------------------------------------------------------------------

export const orgPolicySchema = z.object({
  recording_enabled: z.boolean(),
  ai_processing_enabled: z.boolean(),
  audio_retention: z.enum(['DISCARD_AFTER_TRANSCRIPTION', 'RETAIN_DAYS']),
  retain_days: z.number(),
  ai_suggestions_enabled: z.boolean(),
  ai_suggestions_require_source: z.boolean(),
  enabled_languages: z.array(z.string()).nullable(),
  guardian_consent_under_age: z.number(),
});
export const userSchema = z.object({
  id: z.string(),
  email: z.string(),
  full_name: z.string(),
  is_active: z.boolean(),
  preferred_language: z.string(),
  mfa_enabled: z.boolean(),
  last_login_at: z.string().nullable(),
  roles: z.array(z.string()),
});
export const roleSchema = z.object({ key: z.string(), name: z.string(), permissions: z.array(z.string()) });
export const practitionerFullSchema = practitionerSchema.extend({
  user_id: z.string(),
  registration_number: z.string().nullable(),
  status: z.string(),
  working_hours: z.array(z.object({ weekday: z.number(), start_time: z.string(), end_time: z.string() })),
});
export const knowledgeDocSchema = z.object({
  id: z.string(),
  title: z.string(),
  publisher: z.string(),
  source: z.string(),
  version: z.string(),
  country: z.string(),
  specialty: z.string().nullable(),
  licence: z.string(),
  approved: z.boolean(),
  retired_at: z.string().nullable(),
  created_by: z.string().nullable(),
  chunk_count: z.number(),
});
export const auditLogSchema = z.object({
  id: z.string(),
  occurred_at: z.string(),
  actor_user_id: z.string().nullable(),
  action: z.string(),
  resource_type: z.string(),
  outcome: z.string(),
  reason: z.string().nullable(),
  ai_involved: z.boolean(),
});
export const speechUsageSchema = z.object({
  provider: z.string(),
  model: z.string(),
  sessions: z.number(),
  audio_seconds: z.number(),
  segments: z.number(),
  errors: z.number(),
  fallbacks: z.number(),
  avg_first_segment_latency_ms: z.number().nullable(),
  estimated_cost_paise: z.number().nullable(),
});
export const aiUsageSchema = z.object({
  feature: z.string(),
  provider: z.string(),
  model: z.string(),
  calls: z.number(),
  ok: z.number(),
  failed: z.number(),
  input_tokens: z.number(),
  output_tokens: z.number(),
  tokens_are_estimates: z.boolean(),
  avg_latency_ms: z.number().nullable(),
  estimated_cost_paise: z.number().nullable(),
});
export type OrgPolicy = z.infer<typeof orgPolicySchema>;
export type StaffUser = z.infer<typeof userSchema>;
export type Role = z.infer<typeof roleSchema>;
export type PractitionerFull = z.infer<typeof practitionerFullSchema>;
export type KnowledgeDoc = z.infer<typeof knowledgeDocSchema>;
export type AuditLog = z.infer<typeof auditLogSchema>;

// ---- worklists: orders, results, follow-ups ------------------------------------------------

export const worklistOrderSchema = z.object({
  id: z.string(),
  patient_id: z.string(),
  encounter_id: z.string(),
  category: z.string(),
  name: z.string(),
  priority: z.string(),
  status: z.string(),
  reason: z.string().nullable(),
  ordered_at: z.string().nullable(),
  patient_name: z.string().nullable(),
  patient_mrn: z.string().nullable(),
});

export const reportedResultSchema = z.object({
  id: z.string(),
  patient_id: z.string(),
  service_request_id: z.string(),
  test_name: z.string(),
  value_numeric: z.coerce.number().nullable(),
  value_text: z.string().nullable(),
  unit: z.string().nullable(),
  ref_low: z.coerce.number().nullable(),
  ref_high: z.coerce.number().nullable(),
  interpretation: z.string(),
  comment: z.string().nullable(),
  reported_at: z.string(),
  reviewed_at: z.string().nullable(),
  covering_for: z.string().nullable().optional(),
});

export const worklistFollowUpSchema = z.object({
  id: z.string(),
  patient_id: z.string(),
  encounter_id: z.string(),
  due_date: z.string(),
  kind: z.string(),
  reason: z.string(),
  status: z.string(),
});

export type WorklistOrder = z.infer<typeof worklistOrderSchema>;
export type ReportedResult = z.infer<typeof reportedResultSchema>;
export type WorklistFollowUp = z.infer<typeof worklistFollowUpSchema>;

export const colleagueSchema = z.object({ user_id: z.string(), name: z.string(), specialty: z.string() });
export const coverSchema = z.object({
  id: z.string(),
  from_user_id: z.string(),
  from_name: z.string(),
  to_user_id: z.string(),
  to_name: z.string(),
  starts_on: z.string(),
  ends_on: z.string(),
  active: z.boolean(),
});
export type Colleague = z.infer<typeof colleagueSchema>;
export type Cover = z.infer<typeof coverSchema>;

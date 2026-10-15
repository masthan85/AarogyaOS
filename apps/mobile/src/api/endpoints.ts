import { z } from 'zod';

import { API_BASE_URL, API_PREFIX } from '@/config';
import { secureTokenStore } from '@/services/token-store';

import { ApiClient } from './client';
import {
  aiUsageSchema,
  auditLogSchema,
  knowledgeDocSchema,
  orgPolicySchema,
  practitionerFullSchema,
  roleSchema,
  speechUsageSchema,
  userSchema,
  askSchema,
  documentSchema,
  templateSchema,
  analyseSchema,
  generateSchema,
  reviewBundleSchema,
  reviewResultSchema,
  suggestionActionSchema,
  appointmentSchema,
  clinicalStateSchema,
  encounterDetailSchema,
  encounterSchema,
  consentSchema,
  facilitySchema,
  interactionSchema,
  languageSchema,
  meSchema,
  organisationSchema,
  patientHitSchema,
  noteSchema,
  observationSchema,
  allergySchema,
  conditionSchema,
  medicationSchema,
  orderSchema,
  followUpSchema,
  prescriptionSchema,
  safetyCheckSchema,
  patientConsentsSchema,
  patientSchema,
  policySchema,
  practitionerSchema,
  queueItemSchema,
  slotSchema,
  startInfoSchema,
  timelineEventSchema,
  transcriptSchema,
  tokenPairSchema,
} from './schemas';

let sessionExpiredListener: () => void = () => {};
export const onSessionExpired = (fn: () => void) => {
  sessionExpiredListener = fn;
};

export const api = new ApiClient({
  baseUrl: `${API_BASE_URL}${API_PREFIX}`,
  tokenStore: secureTokenStore,
  onSessionExpired: () => sessionExpiredListener(),
});

export const login = (body: { organisation_slug?: string; email: string; password: string }) =>
  api.request('/auth/login', tokenPairSchema, { method: 'POST', body, auth: false });

export const logout = (refreshToken: string) =>
  api.request('/auth/logout', z.undefined(), {
    method: 'POST',
    body: { refresh_token: refreshToken },
    auth: false,
  });

export const getMe = () => api.request('/auth/me', meSchema);
export const getOrganisation = () => api.request('/organisations/current', organisationSchema);
export const getFacilities = () => api.request('/facilities', z.array(facilitySchema));

// ---- Phase 2 -------------------------------------------------------------------

const qs = (params: Record<string, string | boolean | undefined>) => {
  const q = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&');
  return q ? `?${q}` : '';
};

export type PatientSearch = { name?: string; mobile?: string; mrn?: string };
export const searchPatients = (p: PatientSearch) =>
  api.request(`/patients/search${qs(p)}`, z.array(patientHitSchema));

export type NewPatient = {
  full_name: string;
  age_years?: number;
  date_of_birth?: string;
  administrative_gender: string;
  mobile?: string;
  address?: string;
  preferred_language: string;
  confirm_not_duplicate?: boolean;
};
export const registerPatient = (body: NewPatient) =>
  api.request('/patients', patientSchema, { method: 'POST', body });
export const getPatient = (id: string) => api.request(`/patients/${id}`, patientSchema);
export const getTimeline = (id: string) =>
  api.request(`/patients/${id}/timeline`, z.array(timelineEventSchema));

export const getPractitioners = (facilityId?: string) =>
  api.request(`/practitioners${qs({ facility_id: facilityId })}`, z.array(practitionerSchema));
export const getSlots = (practitionerId: string, on: string) =>
  api.request(`/practitioners/${practitionerId}/slots${qs({ on })}`, z.array(slotSchema));

export const getAppointments = (p: { on: string; facility_id?: string; practitioner_id?: string }) =>
  api.request(`/appointments${qs(p)}`, z.array(appointmentSchema));
export const bookAppointment = (body: {
  patient_id: string;
  practitioner_id: string;
  start_at: string;
  reason?: string;
}) => api.request('/appointments', appointmentSchema, { method: 'POST', body });
const act = (id: string, action: string, body: unknown = {}) =>
  api.request(`/appointments/${id}/${action}`, appointmentSchema, { method: 'POST', body });
export const cancelAppointment = (id: string, reason?: string) => act(id, 'cancel', { reason });
export const checkIn = (id: string, priority: 'ROUTINE' | 'URGENT' = 'ROUTINE') =>
  act(id, 'check-in', { priority });
export const walkIn = (body: {
  patient_id: string;
  facility_id: string;
  practitioner_id?: string;
  priority?: 'ROUTINE' | 'URGENT';
}) => api.request('/walk-ins', appointmentSchema, { method: 'POST', body });
export const getQueue = (facilityId: string, practitionerId?: string) =>
  api.request(
    `/queue${qs({ facility_id: facilityId, practitioner_id: practitionerId })}`,
    z.array(queueItemSchema),
  );

// ---- Phase 3: encounters and the clinical record --------------------------------------

export const startTriage = (appointmentId: string) =>
  api.request('/encounters/triage', encounterSchema, {
    method: 'POST',
    body: { appointment_id: appointmentId },
  });
export const startConsultation = (appointmentId: string) =>
  api.request('/encounters/consultation', encounterSchema, {
    method: 'POST',
    body: { appointment_id: appointmentId },
  });
export const getEncounter = (id: string) => api.request(`/encounters/${id}`, encounterDetailSchema);
export const completeEncounter = (id: string) =>
  api.request(`/encounters/${id}/complete`, encounterSchema, { method: 'POST', body: {} });
export const setTriageCategory = (id: string, category: 'ROUTINE' | 'URGENT' | 'EMERGENCY') =>
  api.request(`/encounters/${id}/triage-category`, encounterSchema, {
    method: 'PUT',
    body: { category },
  });
export const getClinicalState = (patientId: string) =>
  api.request(`/patients/${patientId}/clinical-state`, clinicalStateSchema);

export type VitalsInput = {
  temperature?: { value: number; unit: 'C' | 'F' };
  systolic_bp?: number;
  diastolic_bp?: number;
  heart_rate?: number;
  respiratory_rate?: number;
  spo2?: number;
  height_cm?: number;
  weight_kg?: number;
  blood_glucose_mgdl?: number;
  glucose_context?: 'FASTING' | 'RANDOM' | 'POST_MEAL';
  pain_score?: number;
};
export const recordVitals = (encId: string, body: VitalsInput) =>
  api.request(`/encounters/${encId}/vitals`, z.array(observationSchema), { method: 'POST', body });

export const addNote = (encId: string, body: { note_type: string; content: string; source?: string }) =>
  api.request(`/encounters/${encId}/notes`, noteSchema, { method: 'POST', body });
export const addAllergy = (
  encId: string,
  body: { substance?: string; is_nka?: boolean; severity?: string; certainty?: string; source?: string },
) => api.request(`/encounters/${encId}/allergies`, allergySchema, { method: 'POST', body });
export const addMedication = (encId: string, body: { name: string; dose?: string; frequency?: string }) =>
  api.request(`/encounters/${encId}/medications`, medicationSchema, { method: 'POST', body });
export const addCondition = (
  encId: string,
  body: { display: string; certainty: 'SUSPECTED' | 'PROVISIONAL' | 'CONFIRMED'; category?: string },
) => api.request(`/encounters/${encId}/conditions`, conditionSchema, { method: 'POST', body });
export const confirmCondition = (id: string) =>
  api.request(`/conditions/${id}`, conditionSchema, { method: 'PUT', body: { certainty: 'CONFIRMED' } });
export const verifyFact = (kind: string, id: string, action: 'confirm' | 'reject', reason?: string) =>
  api.request(`/clinical/${kind}/${id}/verify`, z.record(z.string(), z.string()), {
    method: 'POST',
    body: { action, reason },
  });

export type OrderInput = { category: 'LAB' | 'RADIOLOGY' | 'OTHER'; name: string; priority: string; reason?: string };
export const createOrder = (encId: string, body: OrderInput) =>
  api.request(`/encounters/${encId}/orders`, orderSchema, { method: 'POST', body });
export const placeOrder = (id: string) => api.request(`/orders/${id}/place`, orderSchema, { method: 'POST', body: {} });
export const cancelOrder = (id: string, reason: string) =>
  api.request(`/orders/${id}/cancel`, orderSchema, { method: 'POST', body: { reason } });

export type RxItemInput = {
  medicine_name: string;
  strength?: string;
  dose: string;
  route: string;
  frequency: string;
  duration_days?: number;
  instructions?: string;
};
export const createPrescription = (encId: string, items: RxItemInput[]) =>
  api.request(`/encounters/${encId}/prescriptions`, prescriptionSchema, { method: 'POST', body: { items } });
export const safetyCheck = (rxId: string) =>
  api.request(`/prescriptions/${rxId}/safety-check`, safetyCheckSchema, { method: 'POST', body: {} });
export const signPrescription = (rxId: string, acknowledged: string[]) =>
  api.request(`/prescriptions/${rxId}/sign`, prescriptionSchema, {
    method: 'POST',
    body: { acknowledged_warning_codes: acknowledged },
  });
export const voidPrescription = (rxId: string, reason: string) =>
  api.request(`/prescriptions/${rxId}/void`, prescriptionSchema, { method: 'POST', body: { reason } });

export const createFollowUp = (encId: string, body: { due_date: string; reason: string }) =>
  api.request(`/encounters/${encId}/follow-ups`, followUpSchema, { method: 'POST', body });

// ---- Phase 4: languages, consent, recording ---------------------------------------------

export const getLanguages = () => api.request('/languages', z.array(languageSchema));

export const getPatientConsents = (patientId: string) =>
  api.request(`/patients/${patientId}/consents`, patientConsentsSchema);
export const getConsentPolicies = () => api.request('/consent-policies', z.array(policySchema));
export type ConsentInput = {
  purpose: string;
  granted_by_type: 'PATIENT' | 'REPRESENTATIVE';
  representative_name?: string;
  representative_relationship?: string;
  method: 'VERBAL_WITNESSED' | 'ON_DEVICE' | 'PAPER';
  encounter_id?: string;
};
export const captureConsent = (patientId: string, body: ConsentInput) =>
  api.request(`/patients/${patientId}/consents`, consentSchema, { method: 'POST', body });
export const withdrawConsent = (consentId: string, reason?: string) =>
  api.request(`/consents/${consentId}/withdraw`, consentSchema, { method: 'POST', body: { reason } });

export type NewInteraction = {
  patient_id: string;
  purpose: 'RECEPTION' | 'TRIAGE' | 'CONSULTATION';
  encounter_id?: string;
  appointment_id?: string;
  language_hint?: string;
  ai_processing?: boolean;
};
export const createInteraction = (body: NewInteraction) =>
  api.request('/interactions', interactionSchema, { method: 'POST', body });
export const startInteraction = (id: string) =>
  api.request(`/interactions/${id}/start`, startInfoSchema, { method: 'POST', body: {} });
const control = (id: string, action: 'pause' | 'resume' | 'stop') =>
  api.request(`/interactions/${id}/${action}`, interactionSchema, { method: 'POST', body: {} });
export const pauseInteraction = (id: string) => control(id, 'pause');
export const resumeInteraction = (id: string) => control(id, 'resume');
export const stopInteraction = (id: string) => control(id, 'stop');
export const getInteraction = (id: string) => api.request(`/interactions/${id}`, interactionSchema);
export const getTranscript = (id: string, afterSeq = 0) =>
  api.request(`/interactions/${id}/transcript${qs({ after_seq: String(afterSeq) })}`, transcriptSchema);
export const assignSpeaker = (id: string, speakerId: string, role: string) =>
  api.request(`/interactions/${id}/speakers/${encodeURIComponent(speakerId)}`, z.object({ speaker_id: z.string(), role: z.string() }), {
    method: 'PUT',
    body: { role },
  });

/** The gateway authenticates with an access token, so make sure the one we hold is fresh. */
export async function freshAccessToken(): Promise<string> {
  await getMe(); // a 401 here triggers the client's single-flight refresh
  const tokens = await secureTokenStore.load();
  if (!tokens) throw new Error('Not signed in');
  return tokens.accessToken;
}

export const getPatientInteractions = (patientId: string) =>
  api.request(`/patients/${patientId}/interactions`, z.array(interactionSchema));

// ---- Phase 5: AI review queue and suggestions --------------------------------------------

export const analyseInteraction = (interactionId: string) =>
  api.request(`/interactions/${interactionId}/ai/analyse`, analyseSchema, { method: 'POST', body: {} });
export const getReviewBundle = (encId: string) =>
  api.request(`/encounters/${encId}/ai/review`, reviewBundleSchema);
export const reviewCandidate = (
  id: string,
  body: { action: 'accept' | 'edit' | 'reject'; edited_text?: string; mode?: 'note' | 'prescription_draft' },
) => api.request(`/ai/candidates/${id}/review`, reviewResultSchema, { method: 'POST', body });
export const generateSuggestions = (encId: string) =>
  api.request(`/encounters/${encId}/ai/suggestions`, generateSchema, { method: 'POST', body: {} });
export const actOnSuggestion = (
  id: string,
  body: { action: 'accept' | 'edit' | 'reject' | 'dismiss'; title?: string; explanation?: string; reason?: string },
) => api.request(`/ai/suggestions/${id}/action`, suggestionActionSchema, { method: 'POST', body });

// ---- Templates, documents, chart questions -----------------------------------------------------

export const getNoteTemplates = () => api.request('/note-templates', z.array(templateSchema));
export const getDocuments = (encId: string) =>
  api.request(`/encounters/${encId}/summaries`, z.array(documentSchema));
export const draftVisitSummary = (encId: string, body: { instructions?: string; language?: string }) =>
  api.request(`/encounters/${encId}/summaries`, documentSchema, { method: 'POST', body });
export const draftReferralLetter = (
  encId: string,
  body: { recipient: string; reason: string; instructions?: string },
) => api.request(`/encounters/${encId}/letters`, documentSchema, { method: 'POST', body });
export const editDocument = (id: string, content: string) =>
  api.request(`/summaries/${id}`, documentSchema, { method: 'PUT', body: { content } });
export const approveDocument = (id: string) =>
  api.request(`/summaries/${id}/approve`, documentSchema, { method: 'POST', body: {} });
export const askChart = (patientId: string, question: string) =>
  api.request(`/patients/${patientId}/ai/ask`, askSchema, { method: 'POST', body: { question } });
export const getDocumentSpeech = (id: string) =>
  api.requestBytes(`/summaries/${id}/speech`, { method: 'POST', body: {} });

// ---- Administration --------------------------------------------------------------------------------

export const getOrgPolicy = () => api.request('/organisations/current/policy', orgPolicySchema);
export const saveOrgPolicy = (body: z.infer<typeof orgPolicySchema>) =>
  api.request('/organisations/current/policy', orgPolicySchema, { method: 'PUT', body });
export const installConsentWording = (language = 'en-IN') =>
  api.request(`/consent-policies/install-templates${qs({ language })}`, z.array(policySchema), { method: 'POST', body: {} });

export const getUsers = () => api.request('/users', z.array(userSchema));
export const getRoles = () => api.request('/roles', z.array(roleSchema));
export const createUser = (body: { email: string; full_name: string; password: string; roles: string[]; preferred_language?: string }) =>
  api.request('/users', userSchema, { method: 'POST', body });
export const deactivateUser = (id: string) => api.request(`/users/${id}/deactivate`, userSchema, { method: 'POST', body: {} });
export const getPractitionersFull = () => api.request('/practitioners', z.array(practitionerFullSchema));
export const createPractitioner = (body: {
  user_id: string;
  facility_id: string;
  specialty: string;
  registration_number?: string;
  consultation_minutes?: number;
}) => api.request('/practitioners', practitionerFullSchema, { method: 'POST', body });
export const setWorkingHours = (id: string, hours: { weekday: number; start_time: string; end_time: string }[]) =>
  api.request(`/practitioners/${id}/working-hours`, practitionerFullSchema, { method: 'PUT', body: { hours } });

export type TemplateBody = {
  name: string;
  specialty?: string | null;
  sections: { note_type: string; title: string; hint: string }[];
  active: boolean;
};
export const getAllTemplates = () => api.request('/note-templates/all', z.array(templateSchema));
export const createTemplate = (body: TemplateBody) => api.request('/note-templates', templateSchema, { method: 'POST', body });
export const updateTemplate = (id: string, body: TemplateBody) =>
  api.request(`/note-templates/${id}`, templateSchema, { method: 'PUT', body });

export const getKnowledgeDocs = () => api.request('/knowledge/documents', z.array(knowledgeDocSchema));
export const createKnowledgeDoc = (body: {
  title: string;
  publisher: string;
  source: string;
  version: string;
  licence: string;
  specialty?: string;
  chunks: string[];
}) => api.request('/knowledge/documents', knowledgeDocSchema, { method: 'POST', body });
export const approveKnowledgeDoc = (id: string) =>
  api.request(`/knowledge/documents/${id}/approve`, knowledgeDocSchema, { method: 'POST', body: {} });
export const retireKnowledgeDoc = (id: string) =>
  api.request(`/knowledge/documents/${id}/retire`, knowledgeDocSchema, { method: 'POST', body: {} });

export const getAuditLogs = (limit = 50) => api.request(`/audit-logs${qs({ limit: String(limit) })}`, z.array(auditLogSchema));
export const getSpeechUsage = () => api.request('/usage/speech', z.array(speechUsageSchema));
export const getAiUsage = () => api.request('/usage/ai', z.array(aiUsageSchema));

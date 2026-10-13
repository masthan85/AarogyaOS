import { z } from 'zod';

import { API_BASE_URL, API_PREFIX } from '@/config';
import { secureTokenStore } from '@/services/token-store';

import { ApiClient } from './client';
import {
  appointmentSchema,
  clinicalStateSchema,
  encounterDetailSchema,
  encounterSchema,
  facilitySchema,
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
  patientSchema,
  practitionerSchema,
  queueItemSchema,
  slotSchema,
  timelineEventSchema,
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

import { z } from 'zod';

import { API_BASE_URL, API_PREFIX } from '@/config';
import { secureTokenStore } from '@/services/token-store';

import { ApiClient } from './client';
import {
  appointmentSchema,
  facilitySchema,
  meSchema,
  organisationSchema,
  patientHitSchema,
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
export const startConsultation = (id: string) => act(id, 'start-consultation');
export const completeConsultation = (id: string) => act(id, 'complete');
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

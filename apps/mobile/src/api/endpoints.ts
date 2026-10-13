import { z } from 'zod';

import { API_BASE_URL, API_PREFIX } from '@/config';
import { secureTokenStore } from '@/services/token-store';

import { ApiClient } from './client';
import { facilitySchema, meSchema, organisationSchema, tokenPairSchema } from './schemas';

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

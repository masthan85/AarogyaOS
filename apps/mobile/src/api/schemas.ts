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

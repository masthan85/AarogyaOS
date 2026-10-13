import type { Me } from '@/api/schemas';

/**
 * UI affordance only. The backend enforces every permission; hiding a button is never
 * security, it just avoids showing actions that would be refused.
 */
export const can = (me: Me | null | undefined, permission: string): boolean =>
  !!me && me.permissions.includes(permission);

export const ROLE_LABELS: Record<string, string> = {
  super_admin: 'Super Administrator',
  hospital_admin: 'Hospital Administrator',
  clinic_admin: 'Clinic Administrator',
  doctor: 'Doctor',
  nurse: 'Nurse',
  receptionist: 'Receptionist',
  lab_technician: 'Lab Technician',
  radiology_technician: 'Radiology Technician',
  pharmacist: 'Pharmacist',
  billing_staff: 'Billing Staff',
};

export const roleLabel = (key: string): string => ROLE_LABELS[key] ?? key;

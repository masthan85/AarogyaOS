import type { Href } from 'expo-router';

export type DashboardAction = {
  key: string;
  title: string;
  description: string;
  /** UI affordance only; the API enforces the real permission. */
  permission: string;
  href?: Href;
};

// Every tile opens a working screen. Visibility is a convenience; the API enforces permissions.
export const DASHBOARD_ACTIONS: DashboardAction[] = [
  { key: 'patients', title: 'Patients', description: 'Find or register a patient', permission: 'patient:search', href: '/patients' },
  { key: 'appointments', title: 'Appointments', description: 'Day view and booking', permission: 'appointment:read', href: '/appointments' },
  { key: 'queue', title: 'Queue', description: 'Who is waiting, tokens, calling', permission: 'queue:read', href: '/queue' },
  { key: 'facilities', title: 'Facilities', description: 'Sites and departments', permission: 'facility:read', href: '/facilities' },
  { key: 'admin', title: 'Administration', description: 'Settings, staff, doctors, note layouts, reference library, usage and audit', permission: 'user:read', href: '/admin' },
];

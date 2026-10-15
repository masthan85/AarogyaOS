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
  { key: 'results', title: 'Results to review', description: 'Investigation results you ordered, critical first', permission: 'result:review', href: '/results' },
  { key: 'follow-ups', title: 'Follow-ups', description: 'Patients due to be seen again', permission: 'followup:read', href: '/follow-ups' },
  { key: 'lab', title: 'Orders and results', description: 'Pending lab and radiology orders; enter results', permission: 'result:enter', href: '/lab' },
  { key: 'facilities', title: 'Facilities', description: 'Sites and departments', permission: 'facility:read', href: '/facilities' },
  { key: 'admin', title: 'Administration', description: 'Settings, staff, doctors, note layouts, reference library, usage and audit', permission: 'user:read', href: '/admin' },
];

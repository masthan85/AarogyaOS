import type { Href } from 'expo-router';

export type DashboardAction = {
  key: string;
  title: string;
  description: string;
  /** UI affordance only; the API enforces the real permission. */
  permission: string;
  href?: Href;
};

// Clinical workflow tiles are listed so each role sees its future home, but stay disabled
// until the corresponding phase lands. Nothing here pretends to be a working feature.
export const DASHBOARD_ACTIONS: DashboardAction[] = [
  { key: 'patients', title: 'Patients', description: 'Find or register a patient', permission: 'patient:search', href: '/patients' },
  { key: 'appointments', title: 'Appointments', description: 'Day view and booking', permission: 'appointment:read', href: '/appointments' },
  { key: 'queue', title: 'Queue', description: 'Who is waiting, tokens, calling', permission: 'queue:read', href: '/queue' },
  { key: 'facilities', title: 'Facilities', description: 'Sites and departments', permission: 'facility:read', href: '/facilities' },
  { key: 'staff', title: 'Staff & roles', description: 'Phase 1 API ready, screen to follow', permission: 'user:read' },
  { key: 'audit', title: 'Audit log', description: 'Who accessed or changed what', permission: 'audit:read' },
];

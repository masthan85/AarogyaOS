import type { Href } from 'expo-router';

export type DashboardGroup = 'today' | 'clinical' | 'manage';

export type DashboardAction = {
  key: string;
  title: string;
  description: string;
  group: DashboardGroup;
  /** UI affordance only; the API enforces the real permission. */
  permission: string;
  href?: Href;
};

export const GROUP_TITLES: Record<DashboardGroup, string> = {
  today: 'The day at the clinic',
  clinical: 'Clinical work',
  manage: 'Manage',
};
const GROUP_ORDER: DashboardGroup[] = ['today', 'clinical', 'manage'];

// Every tile opens a working screen. Visibility is a convenience; the API enforces permissions.
export const DASHBOARD_ACTIONS: DashboardAction[] = [
  { key: 'queue', title: 'Queue', description: 'Who is waiting, calling', group: 'today', permission: 'queue:read', href: '/queue' },
  { key: 'appointments', title: 'Appointments', description: 'Day view and booking', group: 'today', permission: 'appointment:read', href: '/appointments' },
  { key: 'patients', title: 'Patients', description: 'Find or register', group: 'today', permission: 'patient:search', href: '/patients' },
  { key: 'results', title: 'Results to review', description: 'Critical first', group: 'clinical', permission: 'result:review', href: '/results' },
  { key: 'follow-ups', title: 'Follow-ups', description: 'Due to be seen again', group: 'clinical', permission: 'followup:read', href: '/follow-ups' },
  { key: 'lab', title: 'Orders and results', description: 'Enter lab and radiology results', group: 'clinical', permission: 'result:enter', href: '/lab' },
  { key: 'pharmacy', title: 'Pharmacy', description: 'Signed prescriptions', group: 'clinical', permission: 'prescription:read', href: '/pharmacy' },
  { key: 'facilities', title: 'Facilities', description: 'Sites and departments', group: 'manage', permission: 'facility:read', href: '/facilities' },
  { key: 'admin', title: 'Administration', description: 'Settings, staff, library, audit', group: 'manage', permission: 'user:read', href: '/admin' },
];

/** The tiles a person may see, arranged under their headings in a fixed order. Empty headings are left out. */
export function arrange(
  actions: DashboardAction[],
  allowed: (permission: string) => boolean,
): { group: DashboardGroup; title: string; actions: DashboardAction[] }[] {
  return GROUP_ORDER.map((group) => ({
    group,
    title: GROUP_TITLES[group],
    actions: actions.filter((a) => a.group === group && allowed(a.permission)),
  })).filter((g) => g.actions.length > 0);
}

export const greeting = (hour: number): string =>
  hour < 5 ? 'Good evening' : hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';

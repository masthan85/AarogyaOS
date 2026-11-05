import { router, type Href } from 'expo-router';
import { ScrollView } from 'react-native';

import { useAuth } from '@/auth/AuthProvider';
import { Lead, NavRow } from '@/design-system/components';
import { space } from '@/design-system/tokens';
import { can } from '@/domain/permissions';

const ITEMS: { title: string; description: string; permission: string; href: Href }[] = [
  { title: 'Organisation settings', description: 'Recording, AI and audio-retention switches; patient consent wording', permission: 'org:manage', href: '/admin/policy' },
  { title: 'Staff and doctors', description: 'Accounts and roles, doctor profiles and working hours', permission: 'user:read', href: '/admin/staff' },
  { title: 'Note layouts', description: 'Headings doctors fill in for each kind of visit', permission: 'org:manage', href: '/admin/templates' },
  { title: 'Reference library', description: 'Guidance the software may cite; needs a second person to approve', permission: 'knowledge:manage', href: '/admin/knowledge' },
  { title: 'Usage and audit', description: 'Speech and AI usage, and who did what', permission: 'audit:read', href: '/admin/activity' },
];

export function AdminHome() {
  const { me } = useAuth();
  const items = ITEMS.filter((i) => can(me, i.permission));
  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.sm }}>
      {items.length === 0 ? <Lead>Your role has no administration screens.</Lead> : null}
      {items.map((i) => (
        <NavRow key={i.title} title={i.title} description={i.description} onPress={() => router.push(i.href)} />
      ))}
    </ScrollView>
  );
}

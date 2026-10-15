import { router, type Href } from 'expo-router';
import { Pressable, ScrollView, Text } from 'react-native';

import { useAuth } from '@/auth/AuthProvider';
import { Card } from '@/design-system/components';
import { MIN_TOUCH, space, useTheme } from '@/design-system/tokens';
import { can } from '@/domain/permissions';

const ITEMS: { title: string; description: string; permission: string; href: Href }[] = [
  { title: 'Organisation settings', description: 'Recording, AI and audio-retention switches; patient consent wording', permission: 'org:manage', href: '/admin/policy' },
  { title: 'Staff and doctors', description: 'Accounts and roles, doctor profiles and working hours', permission: 'user:read', href: '/admin/staff' },
  { title: 'Note layouts', description: 'Headings doctors fill in for each kind of visit', permission: 'org:manage', href: '/admin/templates' },
  { title: 'Reference library', description: 'Guidance the software may cite; needs a second person to approve', permission: 'knowledge:manage', href: '/admin/knowledge' },
  { title: 'Usage and audit', description: 'Speech and AI usage, and who did what', permission: 'audit:read', href: '/admin/activity' },
];

export function AdminHome() {
  const t = useTheme();
  const { me } = useAuth();
  const items = ITEMS.filter((i) => can(me, i.permission));
  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md }}>
      {items.length === 0 ? <Text style={{ color: t.textMuted }}>Your role has no administration screens.</Text> : null}
      {items.map((i) => (
        <Pressable key={i.title} accessibilityRole="button" onPress={() => router.push(i.href)} style={{ minHeight: MIN_TOUCH }}>
          <Card title={i.title}>
            <Text style={{ color: t.textMuted }}>{i.description}</Text>
          </Card>
        </Pressable>
      ))}
    </ScrollView>
  );
}

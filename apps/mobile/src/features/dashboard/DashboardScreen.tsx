import { useQuery } from '@tanstack/react-query';
import { router } from 'expo-router';
import { Pressable, ScrollView, Text, useWindowDimensions, View } from 'react-native';

import { getOrganisation } from '@/api/endpoints';
import { useAuth } from '@/auth/AuthProvider';
import { Button, Card, StatusChip } from '@/design-system/components';
import { MIN_TOUCH, space, useTheme } from '@/design-system/tokens';
import { can, roleLabel } from '@/domain/permissions';

import { DASHBOARD_ACTIONS } from './actions';

export function DashboardScreen() {
  const t = useTheme();
  const { me } = useAuth();
  const { width } = useWindowDimensions();
  // 1 column on phones, 2 on small tablets, 3 on large/landscape tablets.
  const columns = width >= 1000 ? 3 : width >= 640 ? 2 : 1;
  const org = useQuery({ queryKey: ['organisation'], queryFn: getOrganisation, enabled: can(me, 'org:read') });

  if (!me) return null;
  const actions = DASHBOARD_ACTIONS.filter((a) => can(me, a.permission));

  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md }}>
      <Card>
        <Text style={{ color: t.text, fontSize: 22, fontWeight: '800' }}>{me.full_name}</Text>
        <Text style={{ color: t.textMuted }}>{org.data?.name ?? (me.organisation_id ? '' : 'Platform')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
          {me.roles.map((r) => (
            <StatusChip key={r} label={roleLabel(r)} tone="success" />
          ))}
        </View>
      </Card>

      {actions.length === 0 ? (
        <Card title="Your workspace">
          <Text style={{ color: t.textMuted }}>
            Workflow screens for your role arrive in upcoming releases.
          </Text>
        </Card>
      ) : (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.md }}>
          {actions.map((a) => (
            <Pressable
              key={a.key}
              accessibilityRole="button"
              accessibilityState={{ disabled: !a.href }}
              disabled={!a.href}
              onPress={() => a.href && router.push(a.href)}
              style={{ flexBasis: columns === 1 ? '100%' : `${100 / columns - 3}%`, flexGrow: 1, minHeight: MIN_TOUCH, opacity: a.href ? 1 : 0.55 }}>
              <Card title={a.title}>
                <Text style={{ color: t.textMuted }}>{a.description}</Text>
                {a.href ? null : <StatusChip label="Coming soon" />}
              </Card>
            </Pressable>
          ))}
        </View>
      )}

      <Button title="Settings" variant="secondary" onPress={() => router.push('/settings')} />
    </ScrollView>
  );
}

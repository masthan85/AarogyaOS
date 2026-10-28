import { useQuery } from '@tanstack/react-query';
import { router } from 'expo-router';
import { Pressable, ScrollView, Text, useWindowDimensions, View } from 'react-native';

import { getFollowUps, getOrganisation, getResultsAwaitingReview } from '@/api/endpoints';
import { useAuth } from '@/auth/AuthProvider';
import { Button, Card, SectionTitle } from '@/design-system/components';
import { elevation, MIN_TOUCH, radius, space, type, useIsDark, useTheme } from '@/design-system/tokens';
import { addDays, toDateString } from '@/domain/dates';
import { can, roleLabel } from '@/domain/permissions';
import { isCritical } from '@/domain/worklists';

import { arrange, DASHBOARD_ACTIONS, greeting } from './actions';

/** A number that wants attention, or a calm zero. Always readable without the colour. */
function Attention({ label, value, hint, hot, onPress }: { label: string; value: number | null; hint: string; hot: boolean; onPress: () => void }) {
  const t = useTheme();
  const dark = useIsDark();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${label}: ${value ?? 'loading'}. ${hint}`}
      onPress={onPress}
      style={[
        { flex: 1, minHeight: MIN_TOUCH * 2, borderRadius: radius.lg, padding: space.md, gap: 2, backgroundColor: hot ? t.warningSoft : t.surface, borderWidth: 1, borderColor: hot ? t.warning : t.border },
        elevation(dark),
      ]}>
      <Text style={[type.display, { color: hot ? t.warning : t.text }]}>{value ?? '–'}</Text>
      <Text style={[type.h3, { color: t.text }]}>{label}</Text>
      <Text style={[type.small, { color: t.textMuted }]}>{hint}</Text>
    </Pressable>
  );
}

export function DashboardScreen() {
  const t = useTheme();
  const dark = useIsDark();
  const { me } = useAuth();
  const { width } = useWindowDimensions();
  // 2 columns on phones, 3 on tablets, 4 on large landscape tablets.
  const columns = width >= 1000 ? 4 : width >= 640 ? 3 : 2;
  const org = useQuery({ queryKey: ['organisation'], queryFn: getOrganisation, enabled: can(me, 'org:read') });
  const canResults = can(me, 'result:review');
  const canFollow = can(me, 'followup:read');
  // gcTime 0 like every list of patient information: nothing lingers in memory after leaving the screen.
  const results = useQuery({ queryKey: ['results-awaiting'], queryFn: getResultsAwaitingReview, enabled: canResults, gcTime: 0 });
  const today = toDateString(new Date());
  const follow = useQuery({ queryKey: ['follow-ups'], queryFn: () => getFollowUps({ status: 'PENDING' }), enabled: canFollow, gcTime: 0 });

  if (!me) return null;
  // The two numbers above already link to these screens, so their tiles are not repeated below.
  const shown = new Set([canResults ? 'results' : '', canFollow ? 'follow-ups' : '']);
  const groups = arrange(DASHBOARD_ACTIONS.filter((a) => !shown.has(a.key)), (p) => can(me, p));
  const critical = results.data?.filter(isCritical).length ?? 0;
  const overdue = follow.data?.filter((f) => f.due_date < today).length ?? 0;
  const dueToday = follow.data?.filter((f) => f.due_date === today).length ?? 0;
  const tile = ({ 2: '50%', 3: '33.333%', 4: '25%' } as const)[columns as 2 | 3 | 4];

  return (
    <ScrollView contentContainerStyle={{ paddingBottom: space.xl }}>
      <View style={{ backgroundColor: t.hero, paddingHorizontal: space.md, paddingTop: space.md, paddingBottom: space.lg, gap: space.xs }}>
        <Text style={[type.small, { color: t.heroMuted }]}>{greeting(new Date().getHours())}</Text>
        <Text style={[type.display, { color: t.heroText }]}>{me.full_name}</Text>
        <Text style={[type.small, { color: t.heroMuted }]}>
          {[org.data?.name ?? (me.organisation_id ? '' : 'Platform'), me.roles.map(roleLabel).join(' · ')].filter(Boolean).join('  ·  ')}
        </Text>
      </View>

      <View style={{ padding: space.md, gap: space.lg }}>
        {canResults || canFollow ? (
          <View style={{ gap: space.sm }}>
            <SectionTitle>Needs your attention</SectionTitle>
            <View style={{ flexDirection: 'row', gap: space.md }}>
              {canResults ? (
                <Attention
                  label="Results to review"
                  value={results.data ? results.data.length : null}
                  hint={critical > 0 ? `${critical} critical` : 'None critical'}
                  hot={critical > 0}
                  onPress={() => router.push('/results')}
                />
              ) : null}
              {canFollow ? (
                <Attention
                  label="Follow-ups"
                  value={follow.data ? overdue + dueToday : null}
                  hint={overdue > 0 ? `${overdue} overdue` : dueToday > 0 ? 'Due today' : 'None due'}
                  hot={overdue > 0}
                  onPress={() => router.push('/follow-ups')}
                />
              ) : null}
            </View>
          </View>
        ) : null}

        {groups.length === 0 ? (
          <Card title="Your workspace">
            <Text style={[type.small, { color: t.textMuted }]}>Workflow screens for your role arrive in upcoming releases.</Text>
          </Card>
        ) : (
          groups.map((g) => (
            <View key={g.group} style={{ gap: space.sm }}>
              <SectionTitle>{g.title}</SectionTitle>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', marginHorizontal: -space.xs }}>
                {g.actions.map((a) => (
                  <View key={a.key} style={{ width: tile, padding: space.xs }}>
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel={`${a.title}. ${a.description}`}
                      onPress={() => a.href && router.push(a.href)}
                      style={({ pressed }) => [
                        { minHeight: MIN_TOUCH * 2, borderRadius: radius.lg, padding: space.md, gap: 4, justifyContent: 'center', backgroundColor: t.surface, borderWidth: 1, borderColor: t.border, opacity: pressed ? 0.85 : 1 },
                        elevation(dark),
                      ]}>
                      <Text style={[type.h3, { color: t.text }]}>{a.title}</Text>
                      <Text style={[type.small, { color: t.textMuted }]}>{a.description}</Text>
                    </Pressable>
                  </View>
                ))}
              </View>
            </View>
          ))
        )}

        <Button title="Settings" variant="ghost" onPress={() => router.push('/settings')} />
      </View>
    </ScrollView>
  );
}

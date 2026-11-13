import { useQuery } from '@tanstack/react-query';
import { router } from 'expo-router';
import { Pressable, ScrollView, Text, useWindowDimensions, View } from 'react-native';

import { getFollowUps, getOrganisation, getResultsAwaitingReview } from '@/api/endpoints';
import { useAuth } from '@/auth/AuthProvider';
import { Card, SectionTitle } from '@/design-system/components';
import { Icon, type IconName } from '@/design-system/icons';
import { elevation, layout, MIN_TOUCH, MIN_TOUCH_SMALL, radius, space, type, useIsDark, useTheme } from '@/design-system/tokens';
import { toDateString } from '@/domain/dates';
import { can, roleLabel } from '@/domain/permissions';
import { isCritical } from '@/domain/worklists';

import { arrange, DASHBOARD_ACTIONS, greeting } from './actions';

type Count = { value: number | null; failed: boolean };

/** A number that wants attention, or a calm zero. Always readable without the colour. */
function Attention({ icon, label, count, hint, hot, onPress }: { icon: IconName; label: string; count: Count; hint: string; hot: boolean; onPress: () => void }) {
  const t = useTheme();
  const dark = useIsDark();
  // Never describe a number that has not arrived: "None critical" beside a blank would be a guess.
  const line = count.failed ? 'Could not load. Open to try again.' : count.value === null ? 'Checking…' : hint;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${label}: ${count.value ?? 'not loaded'}. ${line}`}
      onPress={onPress}
      style={({ pressed }) => [
        { flex: 1, minHeight: MIN_TOUCH * 2, borderRadius: radius.lg, padding: space.md, flexDirection: 'row', alignItems: 'center', gap: space.md, backgroundColor: hot ? t.warningSoft : t.surface, borderWidth: 1, borderColor: hot ? t.warning : t.border, opacity: pressed ? 0.85 : 1 },
        elevation(dark),
      ]}>
      <View style={{ width: 44, height: 44, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center', backgroundColor: hot ? t.surface : t.primarySoft }}>
        <Icon name={icon} size={22} color={hot ? t.warning : t.primary} />
      </View>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={[type.h3, { color: t.text }]}>{label}</Text>
        <Text style={[type.small, { color: hot ? t.warning : t.textMuted, fontWeight: hot ? '700' : '400' }]}>{line}</Text>
      </View>
      <Text style={[type.hero, { color: hot ? t.warning : t.text }]}>{count.value ?? '–'}</Text>
    </Pressable>
  );
}

export function DashboardScreen() {
  const t = useTheme();
  const dark = useIsDark();
  const { me } = useAuth();
  const { width } = useWindowDimensions();
  const wide = width >= layout.wide;
  // 2 columns on phones, 3 from tablet width up (the wide layout caps the column, so 3 still fits).
  const columns = width >= 640 ? 3 : 2;
  const org = useQuery({ queryKey: ['organisation'], queryFn: getOrganisation, enabled: can(me, 'org:read') });
  const canResults = can(me, 'result:review');
  const canFollow = can(me, 'followup:read');
  // gcTime 0 like every list of patient information: nothing lingers in memory after leaving the screen.
  const results = useQuery({ queryKey: ['results-awaiting'], queryFn: getResultsAwaitingReview, enabled: canResults, gcTime: 0 });
  const now = new Date();
  const today = toDateString(now);
  const follow = useQuery({ queryKey: ['follow-ups'], queryFn: () => getFollowUps({ status: 'PENDING' }), enabled: canFollow, gcTime: 0 });

  if (!me) return null;
  // The two numbers above already link to these screens, so their tiles are not repeated below.
  const shown = new Set([canResults ? 'results' : '', canFollow ? 'follow-ups' : '']);
  const groups = arrange(DASHBOARD_ACTIONS.filter((a) => !shown.has(a.key)), (p) => can(me, p));
  const critical = results.data?.filter(isCritical).length ?? 0;
  const overdue = follow.data?.filter((f) => f.due_date < today).length ?? 0;
  const dueToday = follow.data?.filter((f) => f.due_date === today).length ?? 0;
  const tile = columns === 3 ? '33.333%' : '50%';
  const roles = me.roles.map(roleLabel).join(', ');
  const place = org.data?.name ?? (me.organisation_id ? '' : 'Platform');
  const edge = wide ? space.lg : space.md;

  return (
    <ScrollView contentContainerStyle={{ paddingBottom: space.xl, paddingTop: wide ? space.lg : 0 }}>
      <View
        style={{
          backgroundColor: t.hero,
          marginHorizontal: wide ? edge : 0,
          borderRadius: wide ? radius.lg : 0,
          paddingHorizontal: wide ? space.xl : space.md,
          paddingTop: wide ? space.lg : space.sm,
          paddingBottom: wide ? space.xl : space.lg,
          gap: space.md,
        }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', minHeight: MIN_TOUCH_SMALL }}>
          <Text style={[type.small, { color: t.heroMuted, fontWeight: '600' }]}>
            {now.toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' })}
          </Text>
          {wide ? null : (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Settings"
              onPress={() => router.push('/settings')}
              hitSlop={8}
              style={({ pressed }) => ({ width: MIN_TOUCH_SMALL, height: MIN_TOUCH_SMALL, borderRadius: MIN_TOUCH_SMALL / 2, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(255,255,255,0.12)', opacity: pressed ? 0.7 : 1 })}>
              <Icon name="settings" size={20} color={t.heroText} />
            </Pressable>
          )}
        </View>
        <View style={{ gap: space.xs }}>
          <Text style={[type.body, { color: t.heroMuted }]}>{greeting(now.getHours())}</Text>
          <Text style={[type.hero, { color: t.heroText }]}>{me.full_name}</Text>
          <Text style={[type.small, { color: t.heroMuted }]}>{[roles, place].filter(Boolean).join(' at ')}</Text>
        </View>
      </View>

      <View style={{ padding: edge, gap: space.lg }}>
        {canResults || canFollow ? (
          <View style={{ gap: space.sm }}>
            <SectionTitle>Needs your attention</SectionTitle>
            <View style={{ flexDirection: width >= 640 ? 'row' : 'column', gap: space.md }}>
              {canResults ? (
                <Attention
                  icon="activity"
                  label="Results to review"
                  count={{ value: results.data ? results.data.length : null, failed: results.isError }}
                  hint={critical > 0 ? `${critical} critical` : results.data?.length ? 'None critical' : 'Nothing waiting'}
                  hot={critical > 0}
                  onPress={() => router.push('/results')}
                />
              ) : null}
              {canFollow ? (
                <Attention
                  icon="clock"
                  label="Follow-ups"
                  count={{ value: follow.data ? overdue + dueToday : null, failed: follow.isError }}
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
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', margin: -space.xs }}>
                {g.actions.map((a) => (
                  <View key={a.key} style={{ width: tile, padding: space.xs }}>
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel={`${a.title}. ${a.description}`}
                      onPress={() => a.href && router.push(a.href)}
                      style={({ pressed, hovered }: { pressed: boolean; hovered?: boolean }) => [
                        { flex: 1, minHeight: MIN_TOUCH * 2, borderRadius: radius.lg, padding: space.md, gap: space.sm, backgroundColor: t.surface, borderWidth: 1, borderColor: hovered ? t.primary : t.border, opacity: pressed ? 0.85 : 1 },
                        elevation(dark),
                      ]}>
                      <View style={{ width: 40, height: 40, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center', backgroundColor: t.primarySoft }}>
                        <Icon name={a.icon} size={20} color={t.primary} />
                      </View>
                      <View style={{ gap: 2 }}>
                        <Text style={[type.h3, { color: t.text }]}>{a.title}</Text>
                        <Text style={[type.small, { color: t.textMuted }]}>{a.description}</Text>
                      </View>
                    </Pressable>
                  </View>
                ))}
              </View>
            </View>
          ))
        )}
      </View>
    </ScrollView>
  );
}

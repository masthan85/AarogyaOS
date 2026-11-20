import { useQuery } from '@tanstack/react-query';
import { type Href, router } from 'expo-router';
import { Pressable, ScrollView, Text, useWindowDimensions, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { getAppointments, getFollowUps, getOrganisation, getQueue, getResultsAwaitingReview } from '@/api/endpoints';
import type { QueueItem } from '@/api/schemas';
import { useAuth } from '@/auth/AuthProvider';
import { Card, SectionTitle, StatusChip } from '@/design-system/components';
import { Icon, type IconName } from '@/design-system/icons';
import { Reveal } from '@/design-system/motion';
import { elevation, layout, MIN_TOUCH, MIN_TOUCH_SMALL, radius, space, type, useIsDark, useTheme } from '@/design-system/tokens';
import { toDateString } from '@/domain/dates';
import { can, roleLabel } from '@/domain/permissions';
import { isCritical } from '@/domain/worklists';
import { useFacility } from '@/features/facility/useFacility';

import { arrange, DASHBOARD_ACTIONS, greeting } from './actions';

type Metric = {
  key: string;
  icon: IconName;
  label: string;
  value: number | null;
  failed: boolean;
  /** What the number means, said only once the number has arrived. */
  hint: string;
  hot: boolean;
  href: Href;
};

const minutesSince = (iso: string, now: Date) => Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 60000));
const waitLabel = (m: number) => (m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`);

/** One figure for today. The number is never shown with a description it has not earned. */
function MetricTile({ m }: { m: Metric }) {
  const t = useTheme();
  const dark = useIsDark();
  const line = m.failed ? 'Could not load. Open to try again.' : m.value === null ? 'Checking…' : m.hint;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${m.label}: ${m.value ?? 'not loaded'}. ${line}`}
      onPress={() => router.push(m.href)}
      style={({ pressed, hovered }: { pressed: boolean; hovered?: boolean }) => [
        {
          flex: 1,
          minHeight: MIN_TOUCH * 2,
          borderRadius: radius.lg,
          padding: space.md,
          gap: space.sm,
          backgroundColor: m.hot ? t.warningSoft : t.surface,
          borderWidth: 1,
          borderColor: m.hot ? t.warning : hovered ? t.primary : t.border,
          transform: [{ scale: pressed ? 0.98 : 1 }],
        },
        elevation(dark),
      ]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm }}>
        <Icon name={m.icon} size={16} color={m.hot ? t.warning : t.textMuted} />
        <Text style={[type.small, { color: t.textMuted, fontWeight: '600', flex: 1 }]} numberOfLines={1}>{m.label}</Text>
      </View>
      <Text style={[type.hero, { color: m.hot ? t.warning : t.text }]}>{m.value ?? '–'}</Text>
      <Text style={[type.small, { color: m.hot ? t.warning : t.textMuted, fontWeight: m.hot ? '700' : '400' }]} numberOfLines={2}>{line}</Text>
    </Pressable>
  );
}

/** The next few people waiting, so the day's pressure is visible without opening the queue. */
function WaitingNow({ items, failed, loading }: { items: QueueItem[]; failed: boolean; loading: boolean }) {
  const t = useTheme();
  const now = new Date();
  const waiting = items.filter((q) => q.status !== 'IN_CONSULTATION');
  const shown = waiting.slice(0, 5);
  return (
    <Card>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', minHeight: MIN_TOUCH_SMALL }}>
        <Text style={[type.h3, { color: t.text }]}>Next in the queue</Text>
        <Pressable accessibilityRole="link" onPress={() => router.push('/queue')} hitSlop={8} style={{ minHeight: MIN_TOUCH_SMALL, justifyContent: 'center' }}>
          <Text style={[type.small, { color: t.primary, fontWeight: '700' }]}>Open queue</Text>
        </Pressable>
      </View>
      {failed ? (
        <Text style={[type.small, { color: t.danger }]}>Could not load the queue.</Text>
      ) : loading ? (
        <Text style={[type.small, { color: t.textMuted }]}>Checking…</Text>
      ) : shown.length === 0 ? (
        <Text style={[type.small, { color: t.textMuted }]}>Nobody is waiting.</Text>
      ) : (
        shown.map((q, i) => {
          const mins = minutesSince(q.waiting_since, now);
          return (
            <Pressable
              key={q.appointment_id}
              accessibilityRole="button"
              accessibilityLabel={`Token ${q.token_number}, ${q.patient_name}, waiting ${waitLabel(mins)}`}
              onPress={() => router.push('/queue')}
              style={({ hovered }: { pressed: boolean; hovered?: boolean }) => ({
                flexDirection: 'row',
                alignItems: 'center',
                gap: space.md,
                minHeight: MIN_TOUCH,
                paddingVertical: space.xs,
                paddingHorizontal: space.xs,
                borderRadius: radius.md,
                borderTopWidth: i === 0 ? 0 : 1,
                borderTopColor: t.border,
                backgroundColor: hovered ? t.neutralSoft : 'transparent',
              })}>
              <View style={{ width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: t.primarySoft }}>
                <Text style={{ color: t.primary, fontWeight: '800' }}>{q.token_number}</Text>
              </View>
              <View style={{ flex: 1, gap: 2 }}>
                <Text style={{ color: t.text, fontWeight: '600' }} numberOfLines={1}>{q.patient_name}</Text>
                <Text style={[type.caption, { color: t.textMuted, fontWeight: '500' }]} numberOfLines={1}>
                  {q.encounter_status === 'TRIAGE' ? 'Triage started' : 'Not triaged'}{q.practitioner_name ? ` · ${q.practitioner_name}` : ''}
                </Text>
              </View>
              {q.priority === 'URGENT' ? <StatusChip label="Urgent" tone="danger" /> : null}
              <Text style={[type.small, { color: mins >= 30 ? t.warning : t.textMuted, fontWeight: mins >= 30 ? '700' : '500' }]}>{waitLabel(mins)}</Text>
            </Pressable>
          );
        })
      )}
      {waiting.length > shown.length ? (
        <Text style={[type.small, { color: t.textMuted }]}>and {waiting.length - shown.length} more</Text>
      ) : null}
    </Card>
  );
}

export function DashboardScreen() {
  const t = useTheme();
  const dark = useIsDark();
  const { me } = useAuth();
  const { width } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const wide = width >= layout.wide;
  const now = new Date();
  const today = toDateString(now);

  const org = useQuery({ queryKey: ['organisation'], queryFn: getOrganisation, enabled: can(me, 'org:read') });
  const canResults = can(me, 'result:review');
  const canFollow = can(me, 'followup:read');
  const canQueue = can(me, 'queue:read');
  const canAppts = can(me, 'appointment:read');
  const { facilityId } = useFacility();
  // gcTime 0 like every list of patient information: nothing lingers in memory after leaving the screen.
  const results = useQuery({ queryKey: ['results-awaiting'], queryFn: getResultsAwaitingReview, enabled: canResults, gcTime: 0 });
  const follow = useQuery({ queryKey: ['follow-ups'], queryFn: () => getFollowUps({ status: 'PENDING' }), enabled: canFollow, gcTime: 0 });
  const queue = useQuery({ queryKey: ['queue', facilityId], queryFn: () => getQueue(facilityId as string), enabled: canQueue && !!facilityId, gcTime: 0, refetchInterval: 30_000 });
  const appts = useQuery({ queryKey: ['appointments', facilityId, today], queryFn: () => getAppointments({ on: today, facility_id: facilityId }), enabled: canAppts && !!facilityId, gcTime: 0 });

  if (!me) return null;

  const critical = results.data?.filter(isCritical).length ?? 0;
  const overdue = follow.data?.filter((f) => f.due_date < today).length ?? 0;
  const dueToday = follow.data?.filter((f) => f.due_date === today).length ?? 0;
  const waiting = queue.data?.filter((q) => q.status !== 'IN_CONSULTATION') ?? [];
  const longest = waiting.reduce((m, q) => Math.max(m, minutesSince(q.waiting_since, now)), 0);
  const booked = appts.data?.filter((a) => !['CANCELLED', 'NO_SHOW'].includes(a.status)) ?? [];
  const done = booked.filter((a) => a.status === 'COMPLETED').length;

  const metrics: Metric[] = [
    ...(canQueue ? [{
      key: 'queue', icon: 'users' as const, label: 'Waiting now', href: '/queue' as const,
      value: queue.data ? waiting.length : null, failed: queue.isError,
      hint: waiting.length ? `Longest wait ${waitLabel(longest)}` : 'Nobody waiting', hot: longest >= 45,
    }] : []),
    ...(canAppts ? [{
      key: 'appts', icon: 'calendar' as const, label: 'Booked today', href: '/appointments' as const,
      value: appts.data ? booked.length : null, failed: appts.isError,
      hint: booked.length ? `${done} completed` : 'None booked', hot: false,
    }] : []),
    ...(canResults ? [{
      key: 'results', icon: 'activity' as const, label: 'Results to review', href: '/results' as const,
      value: results.data ? results.data.length : null, failed: results.isError,
      hint: critical > 0 ? `${critical} critical` : results.data?.length ? 'None critical' : 'Nothing waiting', hot: critical > 0,
    }] : []),
    ...(canFollow ? [{
      key: 'follow', icon: 'clock' as const, label: 'Follow-ups due', href: '/follow-ups' as const,
      value: follow.data ? overdue + dueToday : null, failed: follow.isError,
      hint: overdue > 0 ? `${overdue} overdue` : dueToday > 0 ? 'Due today' : 'None due', hot: overdue > 0,
    }] : []),
  ];

  // Screens the figures above already open are not repeated as tiles below.
  const shown = new Set(metrics.map((m) => ({ queue: 'queue', appts: 'appointments', results: 'results', follow: 'follow-ups' })[m.key]));
  const groups = arrange(DASHBOARD_ACTIONS.filter((a) => !shown.has(a.key)), (p) => can(me, p));
  const roles = me.roles.map(roleLabel).join(', ');
  const place = org.data?.name ?? (me.organisation_id ? '' : 'Platform');
  const edge = wide ? space.lg : space.md;
  const metricColumns = width >= 640 ? Math.min(metrics.length, 4) : 2;
  const tileWidth = width >= 640 ? '33.333%' : '50%';
  let step = 0;

  return (
    <ScrollView contentContainerStyle={{ paddingBottom: space.xl + insets.bottom, paddingTop: wide ? space.lg + insets.top : 0 }}>
      <Reveal index={step++}>
        <View
          style={{
            backgroundColor: t.hero,
            marginHorizontal: wide ? edge : 0,
            borderRadius: wide ? radius.lg : 0,
            paddingHorizontal: wide ? space.xl : space.md,
            paddingTop: wide ? space.lg : space.sm,
            paddingBottom: wide ? space.xl : space.lg,
            gap: space.md,
            overflow: 'hidden',
          }}>
          {/* Two quiet rings in the corner give the band some depth; they carry no meaning. */}
          <View pointerEvents="none" accessibilityElementsHidden style={{ position: 'absolute', right: -60, top: -80, width: 260, height: 260, borderRadius: 130, borderWidth: 36, borderColor: 'rgba(255,255,255,0.05)' }} />
          <View pointerEvents="none" accessibilityElementsHidden style={{ position: 'absolute', right: 80, bottom: -120, width: 200, height: 200, borderRadius: 100, borderWidth: 24, borderColor: 'rgba(255,255,255,0.04)' }} />
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
      </Reveal>

      <View style={{ padding: edge, gap: space.lg }}>
        {metrics.length ? (
          <Reveal index={step++} style={{ gap: space.sm }}>
            <SectionTitle>Today at a glance</SectionTitle>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', margin: -space.xs }}>
              {metrics.map((m) => (
                <View key={m.key} style={{ width: `${100 / metricColumns}%`, padding: space.xs }}>
                  <MetricTile m={m} />
                </View>
              ))}
            </View>
          </Reveal>
        ) : null}

        {canQueue ? (
          <Reveal index={step++}>
            <WaitingNow items={queue.data ?? []} failed={queue.isError} loading={queue.isPending && !!facilityId} />
          </Reveal>
        ) : null}

        {groups.length === 0 && metrics.length === 0 ? (
          <Card title="Your workspace">
            <Text style={[type.small, { color: t.textMuted }]}>Workflow screens for your role arrive in upcoming releases.</Text>
          </Card>
        ) : (
          groups.map((g) => (
            <Reveal key={g.group} index={step++} style={{ gap: space.sm }}>
              <SectionTitle>{g.title}</SectionTitle>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', margin: -space.xs }}>
                {g.actions.map((a) => (
                  <View key={a.key} style={{ width: tileWidth, padding: space.xs }}>
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel={`${a.title}. ${a.description}`}
                      onPress={() => a.href && router.push(a.href)}
                      style={({ pressed, hovered }: { pressed: boolean; hovered?: boolean }) => [
                        { flex: 1, minHeight: MIN_TOUCH * 2, borderRadius: radius.lg, padding: space.md, gap: space.sm, backgroundColor: t.surface, borderWidth: 1, borderColor: hovered ? t.primary : t.border, transform: [{ scale: pressed ? 0.98 : 1 }] },
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
            </Reveal>
          ))
        )}
      </View>
    </ScrollView>
  );
}

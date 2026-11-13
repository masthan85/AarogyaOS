import { useQuery } from '@tanstack/react-query';
import { ScrollView, Text, View } from 'react-native';

import { getAiUsage, getAuditLogs, getSpeechUsage } from '@/api/endpoints';
import { useAuth } from '@/auth/AuthProvider';
import { Card, EmptyState, LoadingState, SectionTitle, StatusChip } from '@/design-system/components';
import { space, useTheme, type } from '@/design-system/tokens';
import { describeAction } from '@/domain/admin';
import { formatDateTime } from '@/domain/dates';
import { can } from '@/domain/permissions';
import { sentence } from '@/domain/text';

const rupees = (paise: number | null) => (paise === null ? 'cost not configured' : `₹${(paise / 100).toFixed(2)}`);

export function ActivityScreen() {
  const t = useTheme();
  const { me } = useAuth();
  const canUsage = can(me, 'usage:read');
  const speech = useQuery({ queryKey: ['usage-speech'], queryFn: getSpeechUsage, enabled: canUsage, gcTime: 0 });
  const ai = useQuery({ queryKey: ['usage-ai'], queryFn: getAiUsage, enabled: canUsage, gcTime: 0 });
  const audit = useQuery({ queryKey: ['audit'], queryFn: () => getAuditLogs(50), gcTime: 0 });
  if (audit.isPending) return <LoadingState label="Loading activity…" />;

  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md }}>
      {canUsage ? (
        <>
          <SectionTitle>Speech (last 30 days)</SectionTitle>
          {speech.data?.length === 0 ? <EmptyState message="No recordings yet." /> : null}
          {speech.data?.map((r) => (
            <Card key={r.provider + r.model} title={`${r.provider} · ${r.model}`}>
              <Text style={{ color: t.text }}>{r.sessions} sessions, {(r.audio_seconds / 60).toFixed(1)} min of audio, {r.segments} transcript lines</Text>
              <Text style={{ color: r.errors ? t.warning : t.textMuted }}>{r.errors} errors, {r.fallbacks} fallbacks · {rupees(r.estimated_cost_paise)}</Text>
            </Card>
          ))}
          <SectionTitle>AI calls</SectionTitle>
          {ai.data?.length === 0 ? <EmptyState message="No AI calls yet." /> : null}
          {ai.data?.map((r) => (
            <Card key={r.feature + r.provider + r.model} title={`${r.feature} · ${r.provider}`}>
              <Text style={{ color: t.text }}>{r.calls} calls, {r.failed} failed</Text>
              <Text style={{ color: t.textMuted }}>
                {r.input_tokens}/{r.output_tokens} tokens{r.tokens_are_estimates ? ' (estimated)' : ''} · {rupees(r.estimated_cost_paise)}
              </Text>
            </Card>
          ))}
        </>
      ) : null}

      <SectionTitle>Recent activity</SectionTitle>
      <Text style={[type.small, { color: t.textMuted }]}>Who did what, never what was said or written. The latest 50 entries.</Text>
      {audit.data?.length ? (
        <Card>
          {audit.data.map((a, i) => (
            <View
              key={a.id}
              style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: space.sm, paddingVertical: space.sm, borderTopWidth: i === 0 ? 0 : 1, borderTopColor: t.border }}>
              <View style={{ flex: 1, minWidth: 180, gap: 2 }}>
                <Text style={{ color: t.text, fontWeight: '600' }}>{sentence(describeAction(a.action))}</Text>
                <Text style={[type.caption, { color: t.textMuted, fontWeight: '500' }]}>{sentence(a.resource_type)}</Text>
              </View>
              {a.outcome !== 'SUCCESS' ? <StatusChip label={sentence(a.outcome)} tone="danger" /> : null}
              {a.ai_involved ? <StatusChip label="AI involved" tone="ai" /> : null}
              <Text style={[type.small, { color: t.textMuted }]}>{formatDateTime(a.occurred_at)}</Text>
            </View>
          ))}
        </Card>
      ) : null}
    </ScrollView>
  );
}

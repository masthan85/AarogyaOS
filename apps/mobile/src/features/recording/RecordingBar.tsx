import { Text, View } from 'react-native';

import { Button, StatusChip } from '@/design-system/components';
import { radius, space, type, useTheme } from '@/design-system/tokens';
import { formatClock } from '@/domain/recording';

import type { RecordingSession } from './useRecordingSession';

/**
 * Always visible while a session exists, on every tab. Colour AND text change together so the
 * state is unmistakable at a glance and does not depend on colour alone.
 */
export function RecordingBar({ rec }: { rec: RecordingSession }) {
  const t = useTheme();
  if (rec.phase === 'idle') return null;
  const { indicator } = rec;
  const colour = indicator.isRecording ? t.danger : indicator.tone === 'warning' ? t.warning : t.textMuted;
  const live = rec.phase === 'live' || rec.phase === 'starting';

  const bg = indicator.isRecording ? t.dangerSoft : indicator.tone === 'warning' ? t.warningSoft : t.neutralSoft;

  return (
    <View
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      style={{ borderLeftWidth: 4, borderLeftColor: colour, borderRadius: radius.md, padding: space.sm + 2, gap: space.sm, backgroundColor: bg }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm, flexWrap: 'wrap' }}>
        <View style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: indicator.isRecording ? t.danger : 'transparent', borderWidth: 2, borderColor: colour }} />
        <Text style={[type.h3, { color: colour }]}>{indicator.label}</Text>
        <Text style={[type.small, { color: t.text, fontVariant: ['tabular-nums'] }]}>{formatClock(rec.seconds)}</Text>
        {rec.interaction?.ai_processing ? <StatusChip label="AI assist on" tone="ai" /> : null}
      </View>
      {rec.interaction?.is_development || rec.captureKind === 'simulated' ? (
        <Text style={[type.caption, { color: t.warning }]}>
          {[rec.interaction?.is_development ? 'DEVELOPMENT: synthetic transcript' : null, rec.captureKind === 'simulated' ? 'simulated audio' : null].filter(Boolean).join(' · ')}
        </Text>
      ) : null}
      {rec.message ? <Text style={[type.small, { color: t.text }]}>{rec.message}</Text> : null}
      <View style={{ flexDirection: 'row', gap: space.sm }}>
        {live ? (
          <View style={{ flex: 1 }}><Button size="sm" title="Pause" variant="secondary" onPress={() => void rec.pause()} disabled={rec.phase === 'starting'} /></View>
        ) : null}
        {rec.phase === 'paused' ? (
          <View style={{ flex: 1 }}><Button size="sm" title="Resume" onPress={() => void rec.resume()} /></View>
        ) : null}
        {rec.phase !== 'ended' ? (
          <View style={{ flex: 1 }}><Button size="sm" title="Stop" variant="danger" onPress={() => void rec.stop()} /></View>
        ) : null}
      </View>
    </View>
  );
}

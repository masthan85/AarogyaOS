import { Text, View } from 'react-native';

import { Button, StatusChip } from '@/design-system/components';
import { radius, space, useTheme } from '@/design-system/tokens';
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

  return (
    <View
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      style={{ borderWidth: 2, borderColor: colour, borderRadius: radius.md, padding: space.sm, gap: space.sm, backgroundColor: t.surface }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm, flexWrap: 'wrap' }}>
        <View style={{ width: 14, height: 14, borderRadius: 7, backgroundColor: indicator.isRecording ? t.danger : 'transparent', borderWidth: 2, borderColor: colour }} />
        <Text style={{ color: colour, fontWeight: '800', fontSize: 16 }}>{indicator.label}</Text>
        <Text style={{ color: t.text, fontVariant: ['tabular-nums'] }}>{formatClock(rec.seconds)}</Text>
        {rec.interaction?.is_development ? <StatusChip label="DEVELOPMENT · synthetic transcript" tone="warning" /> : null}
        {rec.captureKind === 'simulated' ? <StatusChip label="simulated audio" tone="warning" /> : null}
        {rec.interaction?.ai_processing ? <StatusChip label="AI assist on" tone="ai" /> : null}
      </View>
      {rec.message ? <Text style={{ color: t.text }}>{rec.message}</Text> : null}
      <View style={{ flexDirection: 'row', gap: space.sm }}>
        {live ? (
          <View style={{ flex: 1 }}><Button title="Pause" variant="secondary" onPress={() => void rec.pause()} disabled={rec.phase === 'starting'} /></View>
        ) : null}
        {rec.phase === 'paused' ? (
          <View style={{ flex: 1 }}><Button title="Resume recording" onPress={() => void rec.resume()} /></View>
        ) : null}
        {rec.phase !== 'ended' ? (
          <View style={{ flex: 1 }}><Button title="Stop" variant="danger" onPress={() => void rec.stop()} /></View>
        ) : null}
      </View>
    </View>
  );
}

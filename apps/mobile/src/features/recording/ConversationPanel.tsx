import { useQuery } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, Switch, Text, View } from 'react-native';

import { getPatientConsents } from '@/api/endpoints';
import type { Segment } from '@/api/schemas';
import { Button, Card, ChoiceChips, SectionTitle, StatusChip, TextField } from '@/design-system/components';
import { radius, space, useTheme } from '@/design-system/tokens';
import { formatClock, missingForRecording, needsCheck, shownText, PURPOSE_LABELS, ROLE_LABELS, ROLE_OPTIONS } from '@/domain/recording';

import type { RecordingSession } from './useRecordingSession';

export function ConversationPanel({ rec, patientId, closed, ai, onAiChange }: {
  rec: RecordingSession;
  patientId: string;
  closed: boolean;
  ai: boolean;
  onAiChange: (v: boolean) => void;
}) {
  const t = useTheme();
  const consents = useQuery({ queryKey: ['patient-consents', patientId], queryFn: () => getPatientConsents(patientId), gcTime: 0 });
  const missing = consents.data ? missingForRecording(consents.data.status, ai) : [];
  const simulated = rec.captureKind === 'simulated';
  const idle = rec.phase === 'idle' || rec.phase === 'error';

  return (
    <View style={{ gap: space.md }}>
      {idle ? (
        <Card title="Record this consultation">
          <Text style={{ color: t.textMuted }}>
            Recording starts and stops only when you press the buttons. Everything works without it:
            you can document manually at any time.
          </Text>
          {consents.isPending ? <Text style={{ color: t.textMuted }}>Checking consent…</Text> : null}
          {missing.length > 0 ? (
            <View style={{ gap: space.sm }}>
              <Text style={{ color: t.warning, fontWeight: '700' }}>Consent needed before recording:</Text>
              {missing.map((p) => <Text key={p} style={{ color: t.text }}>• {PURPOSE_LABELS[p] ?? p}</Text>)}
              <Button title="Ask for consent" onPress={() => router.push({ pathname: '/consent/[patientId]', params: { patientId } })} />
            </View>
          ) : null}
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <Text style={{ color: t.text, flex: 1 }}>Let software suggest notes (needs separate consent)</Text>
            <Switch value={ai} onValueChange={onAiChange} accessibilityLabel="AI assistance" />
          </View>
          {simulated ? (
            <Text style={{ color: t.textMuted, fontSize: 12 }}>
              Development build: audio is simulated and the transcript is a scripted sample, not your conversation.
            </Text>
          ) : (
            <Text style={{ color: t.textMuted, fontSize: 12 }}>
              The microphone is used only between Start and Stop, only while this screen is open, and the audio is not saved on this phone.
            </Text>
          )}
          {rec.message ? <Text style={{ color: t.danger }}>{rec.message}</Text> : null}
          <Button title="Start AI consultation" disabled={closed || missing.length > 0 || consents.isPending || rec.phase === 'starting'} onPress={() => void rec.begin()} />
        </Card>
      ) : null}

      <SectionTitle>Conversation</SectionTitle>
      {rec.segments.length === 0 && !rec.partial ? (
        <Text style={{ color: t.textMuted }}>{idle ? 'No recording yet.' : 'Listening… nothing transcribed yet.'}</Text>
      ) : null}
      {rec.segments.map((s) => <Bubble key={s.id} s={s} rec={rec} />)}
      {rec.partial ? (
        <View style={{ padding: space.sm, borderRadius: radius.md, borderWidth: 1, borderStyle: 'dashed', borderColor: t.border }}>
          <Text style={{ color: t.textMuted, fontSize: 12 }}>Listening · not saved</Text>
          <Text style={{ color: t.textMuted, fontStyle: 'italic' }}>{rec.partial.text}…</Text>
        </View>
      ) : null}
      {rec.segments.length > 0 ? (
        <Text style={{ color: t.textMuted, fontSize: 12 }}>
          This is what the speech service heard, plus any corrections staff made (the original is kept). It is not a clinical record until you confirm
          information from it. Tap a speaker label to say who is speaking.
        </Text>
      ) : null}
    </View>
  );
}

function Bubble({ s, rec }: { s: Segment; rec: RecordingSession }) {
  const t = useTheme();
  const [editing, setEditing] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [draft, setDraft] = useState('');
  const [showOriginal, setShowOriginal] = useState(false);
  const role = s.speaker_role;
  const corrected = s.corrected_text != null;
  return (
    <View style={{ padding: space.sm, borderRadius: radius.md, backgroundColor: t.surface, borderWidth: 1, borderColor: needsCheck(s) ? t.warning : t.border, gap: space.xs }}>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: space.sm }}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Change who is speaking"
          disabled={!s.speaker_id}
          onPress={() => setEditing((e) => !e)}
          hitSlop={8}>
          <StatusChip label={`${ROLE_LABELS[role] ?? role}${s.speaker_id ? ` · ${s.speaker_id}` : ''}`} tone={role === 'UNKNOWN' ? 'warning' : 'success'} />
        </Pressable>
        {s.language ? <StatusChip label={s.secondary_language ? `${s.language} + ${s.secondary_language}` : s.language} /> : null}
        {needsCheck(s) ? <StatusChip label="please check" tone="warning" /> : null}
        <Text style={{ color: t.textMuted, fontSize: 12 }}>{formatClock(s.start_ms / 1000)}</Text>
      </View>
      <Text style={{ color: t.text, fontSize: 16 }}>{shownText(s)}</Text>
      {corrected ? (
        <Pressable accessibilityRole="button" onPress={() => setShowOriginal((v) => !v)} hitSlop={8}>
          <Text style={{ color: t.textMuted, fontSize: 12 }}>
            {showOriginal ? `Heard: ${s.raw_text}` : 'Corrected by staff. Tap to see what was heard.'}
          </Text>
        </Pressable>
      ) : null}
      {fixing ? (
        <View style={{ gap: space.sm }}>
          <TextField label="What was actually said" value={draft} onChangeText={setDraft} multiline />
          <View style={{ flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' }}>
            <Button title="Save correction" disabled={!draft.trim()} onPress={() => void rec.correctLine(s.id, draft.trim()).then((ok) => ok && setFixing(false))} />
            {corrected ? <Button title="Undo correction" variant="secondary" onPress={() => void rec.correctLine(s.id, null).then((ok) => ok && setFixing(false))} /> : null}
            <Button title="Cancel" variant="secondary" onPress={() => setFixing(false)} />
          </View>
        </View>
      ) : (
        <Pressable accessibilityRole="button" onPress={() => { setDraft(shownText(s)); setFixing(true); }} hitSlop={8}>
          <Text style={{ color: t.primary, fontSize: 12 }}>Correct this line</Text>
        </Pressable>
      )}
      {editing && s.speaker_id ? (
        <ChoiceChips label="Who is speaking?" value={role as (typeof ROLE_OPTIONS)[number]}
          options={ROLE_OPTIONS.map((r) => ({ value: r, label: ROLE_LABELS[r] }))}
          onChange={(r) => { void rec.assignRole(s.speaker_id as string, r); setEditing(false); }} />
      ) : null}
    </View>
  );
}

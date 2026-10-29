import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Alert, Text, View } from 'react-native';

import { analyseInteraction, getReviewBundle, reviewCandidate } from '@/api/endpoints';
import type { Candidate } from '@/api/schemas';
import { Button, Card, EmptyState, StatusChip, TextField } from '@/design-system/components';
import { radius, space, type, useTheme } from '@/design-system/tokens';
import { ASSERTION_LABELS, canReviewKind, extraAccept, flagLabel, KIND_LABELS } from '@/domain/assist';
import { buildDraft, clearToAccept, progressText, type DraftSection } from '@/domain/emrDraft';
import type { RecordingSession } from '@/features/recording/useRecordingSession';

import { useAction } from './useAction';
import type { EncounterData } from './useEncounterData';

/** One finding the software heard, with the words it came from and the doctor's three choices. */
export function FindingRow({ c, allowed, onDone, showKind }: { c: Candidate; allowed: boolean; onDone: () => void; showKind: boolean }) {
  const t = useTheme();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(c.text);
  const extra = extraAccept(c);
  const accept = useAction(() => reviewCandidate(c.id, { action: 'accept' }), onDone);
  const acceptExtra = useAction(() => reviewCandidate(c.id, { action: 'accept', mode: extra?.mode }), onDone);
  const edit = useAction(() => reviewCandidate(c.id, { action: 'edit', edited_text: text.trim() }), () => { setEditing(false); onDone(); });
  const reject = useAction(() => reviewCandidate(c.id, { action: 'reject' }), onDone);
  const details = Object.entries(c.attributes).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`).join('  ·  ');
  const absent = c.assertion === 'ABSENT';

  return (
    <View style={{ gap: space.xs + 2, paddingVertical: space.sm + 2 }}>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: space.xs + 2 }}>
        <Text style={[type.h3, { color: t.text, flexShrink: 1 }]}>{absent ? `No ${c.text.toLowerCase()}` : c.text}</Text>
        {c.assertion !== 'PRESENT' ? <StatusChip label={ASSERTION_LABELS[c.assertion] ?? c.assertion} tone="warning" /> : null}
        {showKind ? <StatusChip label={KIND_LABELS[c.kind] ?? c.kind} /> : null}
      </View>
      {details ? <Text style={[type.small, { color: t.textMuted }]}>{details}</Text> : null}
      {c.evidence.map((e) => (
        <Text key={e.segment_id} style={[type.small, { color: t.textMuted, fontStyle: 'italic' }]}>
          “{e.quote}” <Text style={{ fontStyle: 'normal', fontWeight: '600' }}>— {e.speaker_role.toLowerCase().replace('_', ' ')}</Text>
        </Text>
      ))}
      {c.risk_flags.map((f) => <Text key={f} style={[type.caption, { color: t.warning }]}>⚠ {flagLabel(f)}</Text>)}
      {!allowed ? <Text style={[type.caption, { color: t.textMuted }]}>The treating doctor reviews this kind of finding.</Text> : null}
      {allowed && editing ? (
        <View style={{ gap: space.sm }}>
          <TextField label="Correct wording" value={text} onChangeText={setText} />
          <View style={{ flexDirection: 'row', gap: space.sm }}>
            <View style={{ flex: 1 }}><Button size="sm" title="Save edit" disabled={!text.trim()} loading={edit.pending} onPress={() => void edit.run()} /></View>
            <View style={{ flex: 1 }}><Button size="sm" title="Cancel" variant="ghost" onPress={() => setEditing(false)} /></View>
          </View>
        </View>
      ) : null}
      {allowed && !editing ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, paddingTop: space.xs }}>
          <Button size="sm" title="Accept" loading={accept.pending} onPress={() => void accept.run()} />
          {extra ? <Button size="sm" title={extra.label} variant="secondary" loading={acceptExtra.pending} onPress={() => void acceptExtra.run()} /> : null}
          <Button size="sm" title="Edit" variant="secondary" onPress={() => setEditing(true)} />
          <Button
            size="sm"
            title="Reject"
            variant="ghost"
            loading={reject.pending}
            onPress={() => Alert.alert('Reject this?', 'It will not be added to the visit.', [{ text: 'Keep', style: 'cancel' }, { text: 'Reject', onPress: () => void reject.run() }])}
          />
        </View>
      ) : null}
    </View>
  );
}

/** A finding already decided: one quiet line. */
function DecidedRow({ c, text, rejected }: { c: Candidate; text: string; rejected: boolean }) {
  const t = useTheme();
  return (
    <View style={{ flexDirection: 'row', gap: space.sm, paddingVertical: space.xs + 2, alignItems: 'flex-start' }}>
      <Text style={{ color: rejected ? t.textMuted : t.success, fontWeight: '800', width: 18 }} accessibilityElementsHidden>{rejected ? '✕' : '✓'}</Text>
      <Text style={[type.body, { flex: 1, color: rejected ? t.textMuted : t.text, textDecorationLine: rejected ? 'line-through' : 'none' }]}>
        {text}
        <Text style={[type.caption, { color: t.textMuted, textDecorationLine: 'none' }]}>
          {'  '}{rejected ? 'Rejected' : c.status === 'EDITED' ? 'Added (edited)' : 'Added'}
        </Text>
      </Text>
    </View>
  );
}

function Section({ s, isDoctor, onDone, onAcceptAll, accepting }: {
  s: DraftSection;
  isDoctor: boolean;
  onDone: () => void;
  onAcceptAll: (ids: string[]) => void;
  accepting: boolean;
}) {
  const t = useTheme();
  const clear = clearToAccept(s.lines);
  const waiting = s.lines.filter((l) => l.state === 'review').length;
  // The heading already names the kind when a section holds only one; the chip is for mixed sections.
  const kinds = new Set(s.lines.map((l) => l.candidate.kind)).size;
  return (
    <Card>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: space.sm }}>
        <Text style={[type.h2, { color: t.text, flex: 1 }]}>{s.title}</Text>
        {waiting > 0 ? <StatusChip label={`${waiting} to review`} tone="ai" /> : null}
      </View>
      {s.lines.length === 0 ? <Text style={[type.small, { color: t.textMuted }]}>Nothing heard. Add it in the Notes tab if it applies.</Text> : null}
      {clear.length > 1 ? (
        <Button size="sm" title={`Accept the ${clear.length} clear items`} variant="secondary" loading={accepting} onPress={() => onAcceptAll(clear.map((c) => c.id))} />
      ) : null}
      {s.lines.map((l, i) => (
        <View key={l.candidate.id} style={{ borderTopWidth: i === 0 ? 0 : 1, borderTopColor: t.border }}>
          {l.state === 'review' ? (
            <FindingRow c={l.candidate} allowed={canReviewKind(l.candidate.kind, isDoctor)} onDone={onDone} showKind={kinds > 1} />
          ) : (
            <DecidedRow c={l.candidate} text={l.text} rejected={l.state === 'rejected'} />
          )}
        </View>
      ))}
    </Card>
  );
}

/**
 * The medical record as the software heard it, laid out like a clinic note, for the doctor to go through.
 * Nothing here is in the record until accepted. Every line shows the words it came from, and an empty
 * heading means nothing was heard about it, not that there is nothing.
 */
export function EmrDraftPanel({ encId, data, rec, isDoctor, onFinish }: {
  encId: string;
  data: EncounterData;
  rec: RecordingSession;
  isDoctor: boolean;
  onFinish: () => void;
}) {
  const t = useTheme();
  const qc = useQueryClient();
  const bundle = useQuery({ queryKey: ['ai-review', encId], queryFn: () => getReviewBundle(encId), gcTime: 0 });
  const [message, setMessage] = useState<string | null>(null);
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['ai-review', encId] });
    void data.refresh();
  };
  const interactionId = rec.interaction?.id;
  const update = useAction(() => analyseInteraction(interactionId as string), (r) => {
    setMessage(r.status === 'FAILED' ? r.message ?? 'AI assistance is unavailable. Carry on documenting manually.' : r.status === 'NOTHING_NEW' ? 'Nothing new to add.' : null);
    refresh();
  });
  const acceptAll = useAction(async (ids: string[]) => {
    for (const id of ids) await reviewCandidate(id, { action: 'accept' }); // one at a time: the visit is locked for each
    return true;
  }, refresh);

  const draft = buildDraft(bundle.data?.candidates ?? []);
  const p = data.patient;
  const share = draft.total === 0 ? 0 : Math.round((draft.reviewed / draft.total) * 100);

  return (
    <View style={{ gap: space.md }}>
      <Card tone="ai">
        <Text style={[type.title, { color: t.text }]}>Draft medical record</Text>
        <Text style={[type.small, { color: t.text, fontWeight: '600' }]}>{p ? `${p.full_name} · ${p.mrn} · ${p.age_years ?? '?'} yrs` : ''}</Text>
        <Text style={[type.small, { color: t.textMuted }]}>
          Prepared by software from the conversation. Nothing is part of the record until you accept it, and nothing is diagnosed or prescribed for
          you. Each line shows the words it came from.
        </Text>
        {draft.total > 0 ? (
          <View style={{ gap: space.xs }} accessible accessibilityLabel={progressText(draft)}>
            <View style={{ height: 8, borderRadius: radius.pill, backgroundColor: t.surface, overflow: 'hidden' }}>
              <View style={{ width: `${share}%`, height: 8, backgroundColor: t.ai }} />
            </View>
            <Text style={[type.caption, { color: t.ai }]}>{progressText(draft)}</Text>
          </View>
        ) : (
          <Text style={[type.small, { color: t.textMuted }]}>{progressText(draft)}</Text>
        )}
        {bundle.data && !bundle.data.ai_enabled ? <Text style={[type.small, { color: t.warning }]}>AI assistance is not switched on for this organisation. Use the Notes tab.</Text> : null}
        {message ? <Text style={[type.small, { color: t.warning }]}>{message}</Text> : null}
        {bundle.isError ? <Text style={[type.small, { color: t.warning }]}>Could not load the draft. The rest of the visit is unaffected.</Text> : null}
        {bundle.data?.ai_enabled ? (
          <Button size="sm" title="Update from the conversation" variant="secondary" loading={update.pending} disabled={!interactionId} onPress={() => void update.run()} />
        ) : null}
      </Card>

      {draft.sections.map((s) => (
        <Section key={s.key} s={s} isDoctor={isDoctor} onDone={refresh} onAcceptAll={(ids) => void acceptAll.run(ids)} accepting={acceptAll.pending} />
      ))}

      {draft.total === 0 && !bundle.isPending ? <EmptyState message="Nothing to review yet. Record the consultation with AI assistance, or write the note yourself." /> : null}
      {draft.total > 0 && draft.pending === 0 ? (
        <Card tone="default">
          <Text style={[type.h2, { color: t.text }]}>Everything reviewed</Text>
          <Text style={[type.small, { color: t.textMuted }]}>Check the Notes, Tests and Prescription tabs for anything the software did not hear, then finish the visit.</Text>
          <Button title="Go to Finish" onPress={onFinish} />
        </Card>
      ) : null}
    </View>
  );
}

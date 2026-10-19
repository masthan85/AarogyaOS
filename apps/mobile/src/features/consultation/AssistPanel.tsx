import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Alert, Text, View } from 'react-native';

import { actOnSuggestion, analyseInteraction, generateSuggestions, getReviewBundle, reviewCandidate } from '@/api/endpoints';
import type { Candidate, Suggestion } from '@/api/schemas';
import { Button, Card, EmptyState, SectionTitle, StatusChip, TextField } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
import {
  acceptOutcome,
  extraAccept, ASSERTION_LABELS, CATEGORY_LABELS, canReviewKind, flagLabel, isSafetyCategory, KIND_LABELS,
  orderSuggestions, pendingCandidates, pendingSuggestions, uncertaintyLabel,
} from '@/domain/assist';
import type { RecordingSession } from '@/features/recording/useRecordingSession';

import { useAction } from './useAction';
import type { EncounterData } from './useEncounterData';

/**
 * Everything here is optional and separate from the record. Candidates and suggestions are
 * proposals; the clinician's accept / edit / reject is what puts anything into the visit.
 * If the AI is unavailable, the rest of the consultation is untouched.
 */
export function AssistPanel({ encId, data, rec, isDoctor }: { encId: string; data: EncounterData; rec: RecordingSession; isDoctor: boolean }) {
  const t = useTheme();
  const qc = useQueryClient();
  const bundle = useQuery({ queryKey: ['ai-review', encId], queryFn: () => getReviewBundle(encId), gcTime: 0 });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['ai-review', encId] });
    void data.refresh();
  };
  const [note, setNote] = useState<string | null>(null);
  const interactionId = rec.interaction?.id;
  const analyse = useAction(
    () => analyseInteraction(interactionId as string),
    (r) => {
      setNote(r.status === 'FAILED' ? r.message ?? 'AI assistance is unavailable. Carry on documenting manually.' : r.status === 'NOTHING_NEW' ? 'Nothing new to look at yet.' : null);
      refresh();
    },
  );
  const suggest = useAction(
    () => generateSuggestions(encId),
    (r) => {
      setNote(r.message ?? null);
      refresh();
    },
  );

  const b = bundle.data;
  const candidates = pendingCandidates(b?.candidates ?? []);
  const suggestions = orderSuggestions(pendingSuggestions(b?.suggestions ?? []));

  return (
    <View style={{ gap: space.md }}>
      <Card title="Software assistance">
        <Text style={{ color: t.textMuted }}>
          These are proposals from software, shown apart from the record. Nothing becomes part of the visit until you accept it, and nothing is
          diagnosed, ordered or prescribed for you. The visit works fully without this tab.
        </Text>
        {b && !b.ai_enabled ? <Text style={{ color: t.warning }}>AI assistance is not switched on for this organisation.</Text> : null}
        {note ? <Text style={{ color: t.warning }}>{note}</Text> : null}
        {b?.ai_enabled ? (
          <Button
            title="Look at the conversation so far"
            variant="secondary"
            loading={analyse.pending}
            disabled={!interactionId}
            onPress={() => void analyse.run()}
          />
        ) : null}
        {b?.ai_enabled && !interactionId ? <Text style={{ color: t.textMuted, fontSize: 12 }}>Start a recording with AI assistance to use this.</Text> : null}
        {b?.suggestions_enabled ? <Button title="Check for things to consider" variant="secondary" loading={suggest.pending} onPress={() => void suggest.run()} /> : null}
      </Card>

      <SectionTitle>From the conversation ({candidates.length})</SectionTitle>
      {bundle.isError ? <Text style={{ color: t.warning }}>Could not load suggestions. The rest of the visit is unaffected.</Text> : null}
      {candidates.length === 0 && !bundle.isPending ? <EmptyState message="Nothing waiting for your review." /> : null}
      {candidates.map((c) => <CandidateCard key={c.id} c={c} allowed={canReviewKind(c.kind, isDoctor)} onDone={refresh} />)}

      {b?.suggestions_enabled ? (
        <>
          <SectionTitle>Things to consider ({suggestions.length})</SectionTitle>
          {suggestions.length === 0 && !bundle.isPending ? <EmptyState message="No suggestions right now." /> : null}
          {suggestions.map((s) => <SuggestionCard key={s.id} s={s} onDone={refresh} />)}
        </>
      ) : null}
    </View>
  );
}

export function CandidateCard({ c, allowed, onDone }: { c: Candidate; allowed: boolean; onDone: () => void }) {
  const t = useTheme();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(c.text);
  const accept = useAction(() => reviewCandidate(c.id, { action: 'accept' }), onDone);
  const extra = extraAccept(c);
  const acceptExtra = useAction(() => reviewCandidate(c.id, { action: 'accept', mode: extra?.mode }), onDone);
  const edit = useAction(() => reviewCandidate(c.id, { action: 'edit', edited_text: text.trim() }), () => { setEditing(false); onDone(); });
  const reject = useAction(() => reviewCandidate(c.id, { action: 'reject' }), onDone);
  const absent = c.assertion === 'ABSENT';
  return (
    <Card>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, alignItems: 'center' }}>
        <StatusChip label="Suggested by software" tone="ai" />
        <StatusChip label={KIND_LABELS[c.kind] ?? c.kind} />
        <StatusChip label={ASSERTION_LABELS[c.assertion] ?? c.assertion} tone={absent ? 'warning' : c.assertion === 'POSSIBLE' ? 'warning' : 'neutral'} />
      </View>
      <Text style={{ color: t.text, fontSize: 17, fontWeight: '700' }}>{absent ? `No ${c.text}` : c.text}</Text>
      {Object.entries(c.attributes).map(([k, v]) => <Text key={k} style={{ color: t.textMuted }}>{k}: {v}</Text>)}
      {c.evidence.map((e) => (
        <View key={e.segment_id} style={{ borderLeftWidth: 3, borderLeftColor: t.border, paddingLeft: space.sm }}>
          <Text style={{ color: t.textMuted, fontSize: 12 }}>Heard from {e.speaker_role.toLowerCase().replace('_', ' ')}</Text>
          <Text style={{ color: t.text, fontStyle: 'italic' }}>“{e.quote}”</Text>
        </View>
      ))}
      {c.risk_flags.map((f) => <Text key={f} style={{ color: t.warning, fontSize: 12 }}>• {flagLabel(f)}</Text>)}
      <Text style={{ color: t.textMuted, fontSize: 12 }}>If accepted: {acceptOutcome(c)}</Text>
      {extra ? <Text style={{ color: t.textMuted, fontSize: 12 }}>Or: {extra.outcome}</Text> : null}
      {!allowed ? <Text style={{ color: t.textMuted, fontSize: 12 }}>The treating doctor reviews this kind of finding.</Text> : null}
      {allowed && editing ? (
        <View style={{ gap: space.sm }}>
          <TextField label="Correct wording" value={text} onChangeText={setText} />
          <Button title="Save as edited" disabled={text.trim().length < 1} loading={edit.pending} onPress={() => void edit.run()} />
          <Button title="Cancel" variant="secondary" onPress={() => setEditing(false)} />
        </View>
      ) : null}
      {allowed && !editing ? (
        <View style={{ flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' }}>
          <Button title="Accept" loading={accept.pending} onPress={() => void accept.run()} />
          {extra ? <Button title={extra.label} variant="secondary" loading={acceptExtra.pending} onPress={() => void acceptExtra.run()} /> : null}
          <Button title="Edit" variant="secondary" onPress={() => setEditing(true)} />
          <Button
            title="Reject"
            variant="secondary"
            loading={reject.pending}
            onPress={() => Alert.alert('Reject this?', 'It will not be added to the visit.', [{ text: 'Keep', style: 'cancel' }, { text: 'Reject', onPress: () => void reject.run() }])}
          />
        </View>
      ) : null}
    </Card>
  );
}

function SuggestionCard({ s, onDone }: { s: Suggestion; onDone: () => void }) {
  const t = useTheme();
  const act = useAction((action: 'accept' | 'reject' | 'dismiss') => actOnSuggestion(s.id, { action }), onDone);
  const safety = isSafetyCategory(s.category);
  return (
    <Card>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, alignItems: 'center' }}>
        <StatusChip label={s.origin === 'MODEL' ? 'Suggested by software' : 'Rule-based check'} tone={s.origin === 'MODEL' ? 'ai' : 'neutral'} />
        <StatusChip label={CATEGORY_LABELS[s.category] ?? s.category} tone={safety ? 'danger' : 'neutral'} />
        {s.origin === 'MODEL' ? <StatusChip label={uncertaintyLabel(s.uncertainty)} tone="warning" /> : null}
      </View>
      <Text style={{ color: t.text, fontSize: 16, fontWeight: '700' }}>{s.title}</Text>
      <Text style={{ color: t.text }}>{s.explanation}</Text>
      {s.uncertainty_note ? <Text style={{ color: t.textMuted }}>{s.uncertainty_note}</Text> : null}
      {s.warnings.map((w) => <Text key={w} style={{ color: t.warning }}>• {w}</Text>)}
      {s.evidence_sources.map((e) => (
        <Text key={e.chunk_id} style={{ color: t.textMuted, fontSize: 12 }}>Source: {e.document}, {e.publisher}, version {e.version}</Text>
      ))}
      {s.category === 'INVESTIGATION' ? <Text style={{ color: t.textMuted, fontSize: 12 }}>If accepted: saved as a draft test you still have to order.</Text> : null}
      <View style={{ flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' }}>
        <Button title={s.category === 'INVESTIGATION' ? 'Add as draft' : 'Noted'} loading={act.pending} onPress={() => void act.run('accept')} />
        <Button title="Not relevant" variant="secondary" onPress={() => void act.run('reject')} />
        <Button title="Hide" variant="secondary" onPress={() => void act.run('dismiss')} />
      </View>
    </Card>
  );
}

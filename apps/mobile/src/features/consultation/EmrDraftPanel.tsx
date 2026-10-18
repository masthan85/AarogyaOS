import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Text, View } from 'react-native';

import { analyseInteraction, getReviewBundle, reviewCandidate } from '@/api/endpoints';
import { Button, Card, EmptyState, SectionTitle, StatusChip } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
import { canReviewKind } from '@/domain/assist';
import { buildDraft, clearToAccept, progressText } from '@/domain/emrDraft';
import type { RecordingSession } from '@/features/recording/useRecordingSession';

import { CandidateCard } from './AssistPanel';
import { useAction } from './useAction';
import type { EncounterData } from './useEncounterData';

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

  return (
    <View style={{ gap: space.md }}>
      <Card title="Draft medical record">
        <Text style={{ color: t.text, fontWeight: '700' }}>{p ? `${p.full_name} · ${p.mrn} · ${p.age_years ?? '?'} yrs` : ''}</Text>
        <Text style={{ color: t.textMuted }}>
          Prepared by software from the conversation. Nothing is part of the record until you accept it, and nothing is diagnosed or prescribed
          for you. Each line shows the words it came from. A heading with nothing under it means nothing was heard about it.
        </Text>
        {bundle.data && !bundle.data.ai_enabled ? <Text style={{ color: t.warning }}>AI assistance is not switched on for this organisation. Use the Notes tab.</Text> : null}
        <StatusChip label={progressText(draft)} tone={draft.pending === 0 && draft.total > 0 ? 'success' : 'warning'} />
        {message ? <Text style={{ color: t.warning }}>{message}</Text> : null}
        {bundle.data?.ai_enabled ? (
          <Button title="Update from the conversation" variant="secondary" loading={update.pending} disabled={!interactionId} onPress={() => void update.run()} />
        ) : null}
        {bundle.isError ? <Text style={{ color: t.warning }}>Could not load the draft. The rest of the visit is unaffected.</Text> : null}
      </Card>

      {draft.sections.map((s) => {
        const clear = clearToAccept(s.lines);
        return (
          <View key={s.key} style={{ gap: space.sm }}>
            <SectionTitle>{s.title}</SectionTitle>
            {s.lines.length === 0 ? <Text style={{ color: t.textMuted }}>Nothing heard. Add it in the Notes tab if it applies.</Text> : null}
            {clear.length > 1 ? (
              <Button title={`Accept the ${clear.length} clear items here`} variant="secondary" loading={acceptAll.pending}
                onPress={() => void acceptAll.run(clear.map((c) => c.id))} />
            ) : null}
            {s.lines.map((l) =>
              l.state === 'review' ? (
                <CandidateCard key={l.candidate.id} c={l.candidate} allowed={canReviewKind(l.candidate.kind, isDoctor)} onDone={refresh} />
              ) : (
                <View key={l.candidate.id} style={{ flexDirection: 'row', gap: space.sm, alignItems: 'center', flexWrap: 'wrap' }}>
                  <StatusChip label={l.state === 'rejected' ? 'Rejected' : l.candidate.status === 'EDITED' ? 'Added (edited)' : 'Added'} tone={l.state === 'rejected' ? 'neutral' : 'success'} />
                  <Text style={{ color: l.state === 'rejected' ? t.textMuted : t.text, textDecorationLine: l.state === 'rejected' ? 'line-through' : 'none', flexShrink: 1 }}>{l.text}</Text>
                </View>
              ),
            )}
          </View>
        );
      })}

      {draft.total === 0 && !bundle.isPending ? <EmptyState message="Nothing to review yet. Record the consultation with AI assistance, or write the note yourself." /> : null}
      {draft.total > 0 && draft.pending === 0 ? (
        <Card title="Everything reviewed">
          <Text style={{ color: t.textMuted }}>Check the Notes, Tests and Prescription tabs for anything the software did not hear, then finish the visit.</Text>
          <Button title="Go to Finish" onPress={onFinish} />
        </Card>
      ) : null}
    </View>
  );
}

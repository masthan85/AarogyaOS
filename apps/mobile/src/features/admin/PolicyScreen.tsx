import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { ScrollView, Text, View } from 'react-native';

import { getConsentPolicies, getOrgPolicy, installConsentWording, saveOrgPolicy } from '@/api/endpoints';
import type { OrgPolicy } from '@/api/schemas';
import { Button, Card, ChoiceChips, ErrorState, LoadingState, SectionTitle, TextField, ToggleRow } from '@/design-system/components';
import { space, useTheme, type } from '@/design-system/tokens';
import { POLICY_HELP, policyProblem, togglePolicy } from '@/domain/admin';
import { useAction } from '@/features/consultation/useAction';

export function PolicyScreen() {
  const t = useTheme();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['org-policy'], queryFn: getOrgPolicy, gcTime: 0 });
  const wording = useQuery({ queryKey: ['consent-policies'], queryFn: getConsentPolicies, gcTime: 0 });
  const [draft, setDraft] = useState<OrgPolicy | null>(null);
  const [days, setDays] = useState('30');
  useEffect(() => {
    if (q.data) {
      setDraft(q.data);
      setDays(String(q.data.retain_days));
    }
  }, [q.data]);
  const save = useAction(() => saveOrgPolicy({ ...(draft as OrgPolicy), retain_days: Number(days) || 0 }), () => void qc.invalidateQueries({ queryKey: ['org-policy'] }));
  const install = useAction(() => installConsentWording('en-IN'), () => void wording.refetch());

  if (q.isPending || !draft) return <LoadingState label="Loading settings…" />;
  if (q.isError) return <ErrorState message="Could not load settings." onRetry={() => q.refetch()} />;
  const problem = policyProblem({ ...draft, retain_days: Number(days) || 0 });
  const set = (key: keyof OrgPolicy, v: boolean) => setDraft(togglePolicy(draft, key, v));
  const installed = wording.data?.length ?? 0;

  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md }} keyboardShouldPersistTaps="handled">
      <SectionTitle>Switches</SectionTitle>
      <Card>
        <Text style={{ color: t.textMuted }}>Everything starts off. Turning something on never overrides a patient's own consent.</Text>
        <ToggleRow label="Recording" help={POLICY_HELP.recording_enabled} value={draft.recording_enabled} onChange={(v) => set('recording_enabled', v)} />
        <ToggleRow label="AI processing" help={POLICY_HELP.ai_processing_enabled} value={draft.ai_processing_enabled} onChange={(v) => set('ai_processing_enabled', v)} />
        <ToggleRow label="AI suggestions" help={POLICY_HELP.ai_suggestions_enabled} value={draft.ai_suggestions_enabled} disabled={!draft.ai_processing_enabled} onChange={(v) => set('ai_suggestions_enabled', v)} />
        <ToggleRow label="Suggestions must cite a reference" help={POLICY_HELP.ai_suggestions_require_source} value={draft.ai_suggestions_require_source} onChange={(v) => set('ai_suggestions_require_source', v)} />
      </Card>

      <SectionTitle>Audio</SectionTitle>
      <Card>
        <ChoiceChips
          label="After a recording is transcribed"
          value={draft.audio_retention}
          onChange={(v) => setDraft({ ...draft, audio_retention: v })}
          options={[
            { value: 'DISCARD_AFTER_TRANSCRIPTION', label: 'Delete the audio' },
            ...(draft.recording_enabled ? [{ value: 'RETAIN_DAYS' as const, label: 'Keep for a while' }] : []),
          ]}
        />
        {draft.audio_retention === 'RETAIN_DAYS' ? (
          <TextField label="Days to keep audio" value={days} onChangeText={setDays} keyboardType="number-pad" />
        ) : null}
        <Text style={[type.caption, { color: t.textMuted }]}>Audio is only ever kept when this setting and the patient's separate consent both allow it.</Text>
      </Card>

      {problem ? <Text style={{ color: t.danger }}>{problem}</Text> : null}
      <Button title="Save settings" disabled={!!problem} loading={save.pending} onPress={() => void save.run()} />

      <SectionTitle>Patient consent wording</SectionTitle>
      <Card>
        <Text style={{ color: t.text }}>{installed > 0 ? `${installed} wordings installed.` : 'No consent wording installed: nobody can be recorded until it is.'}</Text>
        <Text style={[type.caption, { color: t.warning }]}>
          The built-in wording is a template and has NOT been reviewed by a lawyer. Have it reviewed for your jurisdiction before relying on it.
        </Text>
        <Button title={installed > 0 ? 'Install again (adds a new version)' : 'Install English wording'} variant="secondary" loading={install.pending} onPress={() => void install.run()} />
      </Card>
      <View style={{ height: space.xl }} />
    </ScrollView>
  );
}

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { ScrollView, Text, View } from 'react-native';

import { getConsentPolicies, getOrgPolicy, installConsentWording, saveOrgPolicy } from '@/api/endpoints';
import type { OrgPolicy } from '@/api/schemas';
import { useAuth } from '@/auth/AuthProvider';
import { Button, Card, ChoiceChips, ErrorState, LoadingState, MultiChips, SectionTitle, TextField, ToggleRow } from '@/design-system/components';
import { space, useTheme, type } from '@/design-system/tokens';
import { parseAllowance, POLICY_HELP, policyProblem, togglePolicy } from '@/domain/admin';
import { ROLE_LABELS, roleLabel } from '@/domain/permissions';
import { useAction } from '@/features/consultation/useAction';

// Clinic roles only: the platform role does not belong to an organisation.
const MFA_ROLES = Object.keys(ROLE_LABELS).filter((r) => r !== 'super_admin');

export function PolicyScreen() {
  const t = useTheme();
  const qc = useQueryClient();
  const { me, retryBoot } = useAuth();
  const q = useQuery({ queryKey: ['org-policy'], queryFn: getOrgPolicy, gcTime: 0 });
  const wording = useQuery({ queryKey: ['consent-policies'], queryFn: getConsentPolicies, gcTime: 0 });
  // What the administrator has changed but not saved. Unchanged fields show the saved value, so a
  // refetch (for example when the window regains focus) never wipes an edit in progress.
  const [edited, setEdited] = useState<OrgPolicy | null>(null);
  const [daysEdit, setDays] = useState<string | null>(null);
  const [speechEdit, setSpeechLimit] = useState<string | null>(null);
  const [aiEdit, setAiLimit] = useState<string | null>(null);
  const setDraft = setEdited;
  const draft = edited ?? q.data ?? null;
  const asText = (n: number | null | undefined) => (n === null || n === undefined ? '' : String(n));
  const days = daysEdit ?? String(q.data?.retain_days ?? 30);
  const speechLimit = speechEdit ?? asText(q.data?.monthly_speech_minutes_limit);
  const aiLimit = aiEdit ?? asText(q.data?.monthly_ai_calls_limit);
  const forget = () => { setEdited(null); setDays(null); setSpeechLimit(null); setAiLimit(null); };
  const speechValue = parseAllowance(speechLimit);
  const aiValue = parseAllowance(aiLimit);
  const save = useAction(
    () => saveOrgPolicy({
      ...(draft as OrgPolicy),
      retain_days: Number(days) || 0,
      monthly_speech_minutes_limit: speechValue as number | null,
      monthly_ai_calls_limit: aiValue as number | null,
    }),
    () => {
      const mine = (draft?.mfa_required_roles ?? []).some((r) => me?.roles.includes(r));
      forget();
      void qc.invalidateQueries({ queryKey: ['org-policy'] });
      if (mine) retryBoot(); // reload who I am, which now asks me to set it up
    },
  );
  const install = useAction(() => installConsentWording('en-IN'), () => void wording.refetch());

  if (q.isPending || !draft) return <LoadingState label="Loading settings…" />;
  if (q.isError) return <ErrorState message="Could not load settings." onRetry={() => q.refetch()} />;
  const problem = policyProblem({ ...draft, retain_days: Number(days) || 0 })
    ?? (speechValue === undefined || aiValue === undefined ? 'An allowance must be a whole number, or empty for no limit.' : null);
  const set = (key: keyof OrgPolicy, v: boolean) => setDraft(togglePolicy(draft, key, v));
  const installed = wording.data?.length ?? 0;

  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md }} keyboardShouldPersistTaps="handled" automaticallyAdjustKeyboardInsets>
      <SectionTitle>Switches</SectionTitle>
      <Card>
        <Text style={{ color: t.textMuted }}>Everything starts off. Turning something on never overrides a patient's own consent.</Text>
        <ToggleRow label="Recording" help={POLICY_HELP.recording_enabled} value={draft.recording_enabled} onChange={(v) => set('recording_enabled', v)} />
        <ToggleRow label="AI processing" help={POLICY_HELP.ai_processing_enabled} value={draft.ai_processing_enabled} onChange={(v) => set('ai_processing_enabled', v)} />
        <ToggleRow label="AI suggestions" help={POLICY_HELP.ai_suggestions_enabled} value={draft.ai_suggestions_enabled} disabled={!draft.ai_processing_enabled} onChange={(v) => set('ai_suggestions_enabled', v)} />
        <ToggleRow label="Suggestions must cite a reference" help={POLICY_HELP.ai_suggestions_require_source} value={draft.ai_suggestions_require_source} onChange={(v) => set('ai_suggestions_require_source', v)} />
      </Card>

      <SectionTitle>Devices</SectionTitle>
      <Card>
        <ToggleRow
          label="Block screenshots and screen recording"
          help="On Android, staff cannot screenshot or record the app and it is blanked in the recent-apps view. On iPhone and iPad it is hidden from screen recordings; Apple does not let apps block screenshots. Browsers cannot block either."
          value={draft.protect_screens}
          onChange={(v) => setDraft({ ...draft, protect_screens: v })}
        />
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

      <SectionTitle>Two-step sign-in</SectionTitle>
      <Card>
        <Text style={{ color: t.textMuted }}>
          People in the roles you choose must use an authenticator app when they sign in. Anyone who has not set it up yet is asked to before they can do anything else.
        </Text>
        <MultiChips
          label="Required for"
          options={MFA_ROLES.map((r) => ({ value: r, label: roleLabel(r) }))}
          value={draft.mfa_required_roles}
          onChange={(v) => setDraft({ ...draft, mfa_required_roles: v })}
        />
        {draft.mfa_required_roles.some((r) => me?.roles.includes(r)) ? (
          <Text style={[type.small, { color: t.warning }]}>This includes your own role: after saving you will be asked to set it up before continuing.</Text>
        ) : null}
      </Card>

      <SectionTitle>Monthly allowances</SectionTitle>
      <Card>
        <Text style={{ color: t.textMuted }}>
          Leave empty for no limit. When an allowance is used up, new recordings or software assistance switch off until next month. Every visit can still be documented by hand.
        </Text>
        <TextField label="Speech minutes a month" value={speechLimit} onChangeText={setSpeechLimit} keyboardType="number-pad" placeholder="No limit" />
        <TextField label="AI requests a month" value={aiLimit} onChangeText={setAiLimit} keyboardType="number-pad" placeholder="No limit" />
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

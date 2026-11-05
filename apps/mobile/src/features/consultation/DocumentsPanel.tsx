import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Alert, Text, View } from 'react-native';

import { approveDocument, draftReferralLetter, draftVisitSummary, editDocument, getDocuments, getDocumentSpeech } from '@/api/endpoints';
import type { ClinicalDocument } from '@/api/schemas';
import { Button, Card, ChoiceChips, EmptyState, SectionTitle, StatusChip, TextField } from '@/design-system/components';
import { space, useTheme, type } from '@/design-system/tokens';
import { canReadAloud, currentDocuments, documentTitle, translationNote } from '@/domain/documents';
import { LANGUAGE_OPTIONS } from '@/domain/languages';
import { documentHtml, type Letterhead } from '@/domain/print';
import { printHtml, sharePdf } from '@/services/print';
import { type Playback, playWav } from '@/services/audio/playback';

import { useAction } from './useAction';

/**
 * Documents for this visit: a summary for the patient and referral letters. They are assembled
 * from recorded, non-rejected data plus the doctor's own words (no model writes them), then the
 * doctor edits and approves. An approved document cannot be changed; a new draft replaces it.
 */
export function DocumentsPanel({ encId, patientLanguage, letterhead }: { encId: string; patientLanguage?: string; letterhead: Letterhead | null }) {
  const t = useTheme();
  const qc = useQueryClient();
  const docs = useQuery({ queryKey: ['documents', encId], queryFn: () => getDocuments(encId), gcTime: 0 });
  const refresh = () => void qc.invalidateQueries({ queryKey: ['documents', encId] });
  const [advice, setAdvice] = useState('');
  const [language, setLanguage] = useState('en-IN');
  const preferred = patientLanguage && patientLanguage !== 'en-IN' ? patientLanguage : null;
  const [recipient, setRecipient] = useState('');
  const [reason, setReason] = useState('');
  const [extra, setExtra] = useState('');
  const summary = useAction(() => draftVisitSummary(encId, { instructions: advice.trim() || undefined, language }), () => { setAdvice(''); refresh(); });
  const letter = useAction(
    () => draftReferralLetter(encId, { recipient: recipient.trim(), reason: reason.trim(), instructions: extra.trim() || undefined }),
    () => { setRecipient(''); setReason(''); setExtra(''); refresh(); },
  );
  const list = currentDocuments(docs.data ?? []);
  return (
    <View style={{ gap: space.md }}>
      <SectionTitle>Documents</SectionTitle>
      {list.length === 0 && !docs.isPending ? <EmptyState message="No documents yet for this visit." /> : null}
      {list.map((d) => <DocumentCard key={d.id} doc={d} letterhead={letterhead} onChanged={refresh} />)}

      <Card title="New visit summary for the patient">
        <TextField label="Advice in your own words" value={advice} onChangeText={setAdvice} multiline />
        {preferred ? (
          <ChoiceChips label="Language" value={language} onChange={setLanguage}
            options={[{ value: 'en-IN', label: 'English' }, { value: preferred, label: LANGUAGE_OPTIONS.find((l) => l.tag === preferred)?.label ?? preferred }]} />
        ) : null}
        <Button title="Draft summary" loading={summary.pending} onPress={() => void summary.run()} />
        <Text style={[type.caption, { color: t.textMuted }]}>
          Lists signed medicines, ordered tests, follow-ups and settled diagnoses. Suspected diagnoses are left out.
        </Text>
      </Card>
      <Card title="New referral letter">
        <TextField label="To (name and department)" value={recipient} onChangeText={setRecipient} />
        <TextField label="Reason for referral" value={reason} onChangeText={setReason} multiline />
        <TextField label="Anything else to add (optional)" value={extra} onChangeText={setExtra} multiline />
        <Button title="Draft letter" disabled={recipient.trim().length < 2 || reason.trim().length < 3} loading={letter.pending} onPress={() => void letter.run()} />
        <Text style={[type.caption, { color: t.textMuted }]}>
          Includes recorded diagnoses (with how certain they are), allergies, medicines, notes and results. Anything the patient reported but nobody has checked is marked as such.
        </Text>
      </Card>
    </View>
  );
}

function DocumentCard({ doc, letterhead, onChanged }: { doc: ClinicalDocument; letterhead: Letterhead | null; onChanged: () => void }) {
  const t = useTheme();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(doc.content);
  const save = useAction(() => editDocument(doc.id, text), () => { setEditing(false); onChanged(); });
  const approve = useAction(() => approveDocument(doc.id), onChanged);
  const draft = doc.status === 'DRAFT';
  const html = letterhead ? documentHtml(doc, letterhead, letterhead.doctor) : null;
  const share = useAction(async () => { if (html) await sharePdf(html, documentTitle(doc)); });
  const print = useAction(async () => { if (html) await printHtml(html); });
  const [playing, setPlaying] = useState<Playback | null>(null);
  const listen = useAction(
    async () => playWav(await getDocumentSpeech(doc.id), () => setPlaying(null)),
    setPlaying,
  );
  const note = translationNote(doc);
  return (
    <Card>
      <View style={{ flexDirection: 'row', gap: space.sm, flexWrap: 'wrap', alignItems: 'center' }}>
        <Text style={{ color: t.text, fontWeight: '700', flexShrink: 1 }}>{documentTitle(doc)}</Text>
        <StatusChip label={draft ? 'Draft' : 'Approved'} tone={draft ? 'warning' : 'success'} />
        <StatusChip label={`v${doc.version}`} />
      </View>
      {note ? <Text style={{ color: t.warning }}>{note}</Text> : null}
      {editing ? (
        <View style={{ gap: space.sm }}>
          <TextField label="Text" value={text} onChangeText={setText} multiline />
          <Button title="Save changes" disabled={!text.trim()} loading={save.pending} onPress={() => void save.run()} />
          <Button title="Cancel" variant="secondary" onPress={() => { setText(doc.content); setEditing(false); }} />
        </View>
      ) : (
        <Text selectable style={{ color: t.text }}>{doc.content}</Text>
      )}
      {draft && !editing ? (
        <View style={{ flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' }}>
          <Button title="Edit" variant="secondary" onPress={() => setEditing(true)} />
          <Button
            title="Approve"
            loading={approve.pending}
            onPress={() =>
              Alert.alert('Approve this document?', 'Once approved it cannot be changed. You can draft a new version.', [
                { text: 'Not yet', style: 'cancel' },
                { text: 'Approve', onPress: () => void approve.run() },
              ])
            }
          />
        </View>
      ) : null}
      {html ? (
        <View style={{ flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' }}>
          <Button title="Share as PDF" variant="secondary" loading={share.pending} onPress={() => void share.run()} />
          <Button title="Print" variant="secondary" loading={print.pending} onPress={() => void print.run()} />
        </View>
      ) : null}
      {canReadAloud(doc) ? (
        playing ? (
          <Button title="Stop" variant="secondary" onPress={() => { playing.stop(); setPlaying(null); }} />
        ) : (
          <Button title="Listen" variant="secondary" loading={listen.pending} onPress={() => void listen.run()} />
        )
      ) : null}
      {!draft ? <Text style={[type.caption, { color: t.textMuted }]}>Approved. Sharing and printing use this phone only; nothing is sent from the server. Reading aloud uses the AI service and needs the patient's consent.</Text> : null}
    </Card>
  );
}

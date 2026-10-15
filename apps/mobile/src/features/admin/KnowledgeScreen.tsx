import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Alert, ScrollView, Text } from 'react-native';

import { approveKnowledgeDoc, createKnowledgeDoc, getKnowledgeDocs, retireKnowledgeDoc } from '@/api/endpoints';
import type { KnowledgeDoc } from '@/api/schemas';
import { useAuth } from '@/auth/AuthProvider';
import { Button, Card, ChoiceChips, EmptyState, LoadingState, SectionTitle, StatusChip, TextField } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
import { approvalState, splitPassages } from '@/domain/admin';
import { useAction } from '@/features/consultation/useAction';

const LICENCES = [
  { value: 'ORG_LICENSED', label: 'Our organisation is licensed to use it' },
  { value: 'PUBLIC_DOMAIN', label: 'Public domain' },
  { value: 'SYNTHETIC_TEST', label: 'Test text only' },
];

export function KnowledgeScreen() {
  const t = useTheme();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['knowledge'], queryFn: getKnowledgeDocs, gcTime: 0 });
  const refresh = () => void qc.invalidateQueries({ queryKey: ['knowledge'] });
  const [title, setTitle] = useState('');
  const [publisher, setPublisher] = useState('');
  const [source, setSource] = useState('');
  const [version, setVersion] = useState('');
  const [licence, setLicence] = useState('ORG_LICENSED');
  const [text, setText] = useState('');
  const passages = splitPassages(text);
  const valid = title.trim().length >= 3 && publisher.trim().length >= 2 && source.trim().length >= 2 && version.trim() && passages.length > 0;
  const add = useAction(
    () => createKnowledgeDoc({ title: title.trim(), publisher: publisher.trim(), source: source.trim(), version: version.trim(), licence, chunks: passages }),
    () => { setTitle(''); setPublisher(''); setSource(''); setVersion(''); setText(''); refresh(); },
  );
  if (q.isPending) return <LoadingState label="Loading library…" />;

  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md }} keyboardShouldPersistTaps="handled">
      <SectionTitle>Reference documents</SectionTitle>
      <Text style={{ color: t.textMuted }}>Software suggestions may cite only approved documents. Whoever adds a document cannot approve it.</Text>
      {q.data?.length === 0 ? <EmptyState message="No documents yet." /> : null}
      {q.data?.map((d) => <DocCard key={d.id} doc={d} onChanged={refresh} />)}

      <Card title="Add a document">
        <Text style={{ color: t.warning, fontSize: 12 }}>
          Add only text you have the right to use. Nothing is copied from the internet for you, and no clinical content ships with the app.
        </Text>
        <TextField label="Title" value={title} onChangeText={setTitle} />
        <TextField label="Publisher" value={publisher} onChangeText={setPublisher} />
        <TextField label="Where it comes from (name, link or reference)" value={source} onChangeText={setSource} />
        <TextField label="Version or date" value={version} onChangeText={setVersion} />
        <ChoiceChips label="Rights" value={licence} onChange={setLicence} options={LICENCES} />
        <TextField label="Text: separate passages with a blank line" value={text} onChangeText={setText} multiline />
        <Text style={{ color: t.textMuted, fontSize: 12 }}>{passages.length} passage(s)</Text>
        <Button title="Add for approval" disabled={!valid} loading={add.pending} onPress={() => void add.run()} />
      </Card>
    </ScrollView>
  );
}

function DocCard({ doc, onChanged }: { doc: KnowledgeDoc; onChanged: () => void }) {
  const t = useTheme();
  const { me } = useAuth();
  const state = approvalState(doc, me?.id ?? '');
  const approve = useAction(() => approveKnowledgeDoc(doc.id), onChanged);
  const retire = useAction(() => retireKnowledgeDoc(doc.id), onChanged);
  return (
    <Card title={doc.title}>
      <Text style={{ color: t.textMuted }}>{doc.publisher} · version {doc.version} · {doc.chunk_count} passages</Text>
      <StatusChip label={state === 'approved' ? 'Approved: in use' : state === 'retired' ? 'Retired' : 'Waiting for approval'} tone={state === 'approved' ? 'success' : 'warning'} />
      {state === 'own' ? <Text style={{ color: t.textMuted, fontSize: 12 }}>You added this, so another administrator must approve it.</Text> : null}
      {state === 'ready' ? (
        <Button title="Approve for use" loading={approve.pending}
          onPress={() => Alert.alert('Approve this document?', 'Software suggestions may then cite it. Read it first: you are vouching for its content.', [
            { text: 'Not yet', style: 'cancel' }, { text: 'Approve', onPress: () => void approve.run() }])} />
      ) : null}
      {state !== 'retired' ? (
        <Button title="Retire" variant="secondary" loading={retire.pending}
          onPress={() => Alert.alert('Retire this document?', 'It stops being used straight away.', [
            { text: 'Keep', style: 'cancel' }, { text: 'Retire', style: 'destructive', onPress: () => void retire.run() }])} />
      ) : null}
    </Card>
  );
}

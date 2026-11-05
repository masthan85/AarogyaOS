import { useState } from 'react';
import { Text, View } from 'react-native';

import { askChart } from '@/api/endpoints';
import type { AskResult } from '@/api/schemas';
import { Button, Card, StatusChip, TextField } from '@/design-system/components';
import { space, useTheme, type } from '@/design-system/tokens';

import { useAction } from './useAction';

/**
 * Ask a question about this patient's recorded chart. Answers cite the entries they rest on and
 * never come from outside the chart; a plain list of matching entries is always shown too, so the
 * feature still works when AI answering is off or unavailable.
 */
export function AskChartCard({ patientId }: { patientId: string }) {
  const t = useTheme();
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState<AskResult | null>(null);
  const ask = useAction(() => askChart(patientId, question.trim()), setResult);
  return (
    <Card title="Ask about this patient's chart">
      <TextField label="Question" value={question} onChangeText={setQuestion} placeholder="e.g. When was the last HbA1c?" returnKeyType="search" />
      <Button title="Ask" disabled={question.trim().length < 3} loading={ask.pending} onPress={() => void ask.run()} />
      {result?.message ? <Text style={{ color: t.warning }}>{result.message}</Text> : null}
      {result?.answer?.map((a, i) => (
        <View key={i} style={{ gap: space.xs, paddingTop: space.xs }}>
          <View style={{ flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' }}>
            <StatusChip label="Answered by software from the chart" tone="ai" />
            {result.is_development ? <StatusChip label="development model" tone="warning" /> : null}
          </View>
          <Text style={[type.body, { color: t.text }]}>{a.text}</Text>
          {a.citations.map((c) => (
            <Text key={c.ref} style={[type.caption, { color: t.textMuted }]}>Source: {c.label}{c.date ? ` · ${c.date}` : ''}</Text>
          ))}
        </View>
      ))}
      {result && result.matches.length > 0 ? (
        <View style={{ gap: space.xs, paddingTop: space.sm }}>
          <Text style={{ color: t.textMuted, fontWeight: '600' }}>Matching entries in the chart</Text>
          {result.matches.map((m) => (
            <Text key={m.ref} style={{ color: t.text }}>• {m.text}{m.date ? ` (${m.date})` : ''}</Text>
          ))}
        </View>
      ) : null}
      {result && result.matches.length === 0 && !result.answered ? <Text style={{ color: t.textMuted }}>Nothing in the recorded chart matches.</Text> : null}
      <Text style={[type.caption, { color: t.textMuted }]}>Only recorded, non-rejected entries are searched. Unreviewed AI suggestions are not part of the chart.</Text>
    </Card>
  );
}

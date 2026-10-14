import { router } from 'expo-router';
import { Alert, Text, View } from 'react-native';

import { completeEncounter } from '@/api/endpoints';
import { AlertBanner, Button, Card, SectionTitle } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';

import { useAction } from './useAction';
import type { EncounterData } from './useEncounterData';

export function FinishPanel({ encId, data }: { encId: string; data: EncounterData }) {
  const t = useTheme();
  const d = data.detail;
  const draftRx = d?.prescriptions.filter((p) => p.status === 'DRAFT').length ?? 0;
  const draftOrders = d?.orders.filter((o) => o.status === 'DRAFT').length ?? 0;
  const unconfirmed = d?.conditions.filter((c) => c.certainty !== 'CONFIRMED').length ?? 0;
  const finish = useAction(() => completeEncounter(encId), () => router.replace('/queue'));

  return (
    <View style={{ gap: space.md }}>
      <SectionTitle>Finish the visit</SectionTitle>
      <Card>
        <Text style={{ color: t.text }}>{d?.notes.length ?? 0} notes · {d?.conditions.length ?? 0} diagnoses · {d?.prescriptions.filter((p) => p.status === 'SIGNED').length ?? 0} signed prescriptions · {d?.orders.filter((o) => o.status !== 'DRAFT' && o.status !== 'CANCELLED').length ?? 0} investigations · {d?.follow_ups.length ?? 0} follow-ups</Text>
        {draftRx > 0 ? <AlertBanner level="WARNING" message={`${draftRx} prescription draft(s) are not signed. Sign or discard them before finishing.`} /> : null}
        {draftOrders > 0 ? <AlertBanner level="WARNING" message={`${draftOrders} investigation draft(s) are not placed. Place or discard them first.`} /> : null}
        {unconfirmed > 0 ? <AlertBanner level="INFO" message={`${unconfirmed} diagnosis(es) are still provisional or suspected.`} /> : null}
        <Button title="Complete visit" disabled={draftRx + draftOrders > 0} loading={finish.pending}
          onPress={() => Alert.alert('Complete this visit?', 'The record becomes read-only.', [
            { text: 'Not yet', style: 'cancel' }, { text: 'Complete', onPress: () => void finish.run() },
          ])} />
      </Card>
    </View>
  );
}

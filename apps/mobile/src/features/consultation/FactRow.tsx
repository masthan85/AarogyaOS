import { Text, View } from 'react-native';

import { Button, ProvenanceChip } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
import { needsVerification, provenance } from '@/domain/clinical';

/** A clinical fact with its provenance, and a confirm action while a clinician still has to check it. */
export function FactRow({
  title,
  detail,
  source,
  verification,
  onConfirm,
}: {
  title: string;
  detail?: string;
  source: string;
  verification: string;
  onConfirm?: () => void;
}) {
  const t = useTheme();
  const p = provenance(source, verification);
  return (
    <View style={{ gap: space.xs, paddingVertical: space.xs }}>
      <Text style={{ color: t.text, fontWeight: '600' }}>{title}</Text>
      {detail ? <Text style={{ color: t.textMuted }}>{detail}</Text> : null}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm, flexWrap: 'wrap' }}>
        <ProvenanceChip text={p.text} tone={p.tone} />
        {onConfirm && needsVerification(verification) ? <Button title="Confirm" variant="secondary" onPress={onConfirm} /> : null}
      </View>
    </View>
  );
}

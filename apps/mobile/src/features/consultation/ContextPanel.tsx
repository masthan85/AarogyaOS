import { Text, View } from 'react-native';

import { verifyFact } from '@/api/endpoints';
import { AlertBanner, Card, SectionTitle, StatusChip } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
import { formatVital, interpretationLabel, interpretationTone, VITAL_LABELS } from '@/domain/clinical';

import { AskChartCard } from './AskChartCard';
import { FactRow } from './FactRow';
import { useAction } from './useAction';
import type { EncounterData } from './useEncounterData';

/** The prepared picture of the patient: what is known, how reliable it is, what needs attention. */
export function ContextPanel({ data }: { data: EncounterData }) {
  const t = useTheme();
  const verify = useAction(
    (kind: string, id: string) => verifyFact(kind, id, 'confirm'),
    () => void data.refresh(),
  );
  const s = data.state;
  if (!s) return <Text style={{ color: t.textMuted }}>Loading patient context…</Text>;

  return (
    <View style={{ gap: space.md }}>
      {s.alerts.map((a) => <AlertBanner key={a.code + a.message} level={a.level} message={a.message} />)}
      {data.detail ? <AskChartCard patientId={data.detail.encounter.patient_id} /> : null}

      <SectionTitle>Allergies</SectionTitle>
      <Card>
        {s.allergies.length === 0 ? <Text style={{ color: t.warning }}>Not recorded</Text> : null}
        {s.allergies.map((a) => (
          <FactRow key={a.id} title={a.is_nka ? 'No known allergies' : a.substance}
            detail={a.is_nka ? undefined : [a.severity.toLowerCase(), a.certainty.toLowerCase(), a.reaction].filter(Boolean).join(' · ')}
            source={a.source} verification={a.verification_state} onConfirm={() => void verify.run('allergies', a.id)} />
        ))}
      </Card>

      <SectionTitle>Conditions</SectionTitle>
      <Card>
        {s.conditions.length === 0 ? <Text style={{ color: t.textMuted }}>None recorded</Text> : null}
        {s.conditions.map((c) => (
          <FactRow key={c.id} title={c.display} detail={c.certainty.toLowerCase()} source={c.source} verification={c.verification_state} />
        ))}
      </Card>

      <SectionTitle>Current medicines</SectionTitle>
      <Card>
        {s.medications.length === 0 ? <Text style={{ color: t.textMuted }}>None recorded</Text> : null}
        {s.medications.map((m) => (
          <FactRow key={m.id} title={m.name} detail={[m.dose, m.frequency].filter(Boolean).join(' · ') || undefined}
            source={m.source} verification={m.verification_state} onConfirm={() => void verify.run('medications', m.id)} />
        ))}
      </Card>

      <SectionTitle>Latest vitals</SectionTitle>
      <Card>
        {s.latest_vitals.length === 0 ? <Text style={{ color: t.textMuted }}>None recorded</Text> : null}
        {s.latest_vitals.map((o) => {
          const label = interpretationLabel(o.interpretation);
          return (
            <View key={o.id} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 2 }}>
              <Text style={{ color: t.text }}>{VITAL_LABELS[o.code] ?? o.code}: {formatVital(o)}</Text>
              {label ? <StatusChip label={label} tone={interpretationTone(o.interpretation)} /> : null}
            </View>
          );
        })}
        {s.bmi !== null ? <Text style={{ color: t.textMuted }}>BMI {s.bmi}</Text> : null}
      </Card>

      {s.results_awaiting_review.length > 0 ? (
        <>
          <SectionTitle>Results awaiting review</SectionTitle>
          <Card>
            {s.results_awaiting_review.map((r) => (
              <View key={r.id} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text style={{ color: t.text }}>{r.test_name}: {r.value_numeric ?? r.value_text} {r.unit ?? ''}</Text>
                {interpretationLabel(r.interpretation) ? <StatusChip label={interpretationLabel(r.interpretation) as string} tone={interpretationTone(r.interpretation)} /> : null}
              </View>
            ))}
          </Card>
        </>
      ) : null}
    </View>
  );
}

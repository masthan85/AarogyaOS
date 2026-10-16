import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { ScrollView, Text, View } from 'react-native';

import { getPatientPrescriptions } from '@/api/endpoints';
import type { PatientHit } from '@/api/schemas';
import { Button, Card, EmptyState, ErrorState, LoadingState, StatusChip } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
import { formatDateTime } from '@/domain/dates';
import { PatientSearchScreen } from '@/features/patients/PatientSearchScreen';

function PrescriptionList({ patient, onBack }: { patient: PatientHit; onBack: () => void }) {
  const t = useTheme();
  const q = useQuery({ queryKey: ['pharmacy-rx', patient.id], queryFn: () => getPatientPrescriptions(patient.id), gcTime: 0 });
  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md }}>
      <Card>
        <Text style={{ color: t.text, fontSize: 18, fontWeight: '700' }}>{patient.full_name}</Text>
        <Text style={{ color: t.textMuted }}>{patient.mrn} · {patient.age_years ?? '?'} yrs</Text>
        <Button title="Choose a different patient" variant="secondary" onPress={onBack} />
      </Card>
      <Text style={{ color: t.textMuted }}>
        Pharmacists see signed prescriptions only. This is a read-only view for checking what the doctor prescribed; it does not record dispensing or stock,
        and it does not check interactions.
      </Text>
      {q.isPending ? <LoadingState /> : null}
      {q.isError ? <ErrorState message="Could not load prescriptions." onRetry={() => void q.refetch()} /> : null}
      {q.data?.length === 0 ? <EmptyState message="No signed prescriptions for this patient." /> : null}
      {q.data?.map((rx) => (
        <Card key={rx.id}>
          <View style={{ flexDirection: 'row', gap: space.sm }}>
            <StatusChip
              label={rx.status === 'SIGNED' ? 'Signed' : rx.status === 'VOIDED' ? 'Voided — do not dispense' : 'Draft — not issued, do not dispense'}
              tone={rx.status === 'SIGNED' ? 'success' : 'danger'}
            />
          </View>
          {rx.signed_at ? <Text style={{ color: t.textMuted, fontSize: 12 }}>Signed {formatDateTime(rx.signed_at)}</Text> : null}
          {rx.items.map((i) => (
            <Text key={i.id} style={{ color: t.text }}>
              {i.position}. {i.medicine_name}{i.strength ? ` ${i.strength}` : ''} — {i.dose}, {i.route.toLowerCase()}, {i.frequency}
              {i.duration_days ? ` for ${i.duration_days} days` : ''}{i.instructions ? ` (${i.instructions})` : ''}
            </Text>
          ))}
        </Card>
      ))}
    </ScrollView>
  );
}

export function PharmacyScreen() {
  const [patient, setPatient] = useState<PatientHit | null>(null);
  return patient ? <PrescriptionList patient={patient} onBack={() => setPatient(null)} /> : <PatientSearchScreen onSelect={setPatient} />;
}

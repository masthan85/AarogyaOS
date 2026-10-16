import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import { getPatientDispensings, getPatientPrescriptions, recordDispensing } from '@/api/endpoints';
import { useAuth } from '@/auth/AuthProvider';
import type { PatientHit } from '@/api/schemas';
import { Button, Card, EmptyState, ErrorState, LoadingState, StatusChip } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
import { formatDateTime } from '@/domain/dates';
import { can } from '@/domain/permissions';
import { dispenseState } from '@/domain/worklists';
import { PatientSearchScreen } from '@/features/patients/PatientSearchScreen';

function PrescriptionList({ patient, onBack }: { patient: PatientHit; onBack: () => void }) {
  const t = useTheme();
  const { me } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['pharmacy-rx', patient.id], queryFn: () => getPatientPrescriptions(patient.id), gcTime: 0 });
  const given = useQuery({ queryKey: ['pharmacy-given', patient.id], queryFn: () => getPatientDispensings(patient.id), gcTime: 0 });
  const record = useMutation({
    mutationFn: (v: { id: string; status: 'DISPENSED' | 'PARTIALLY_DISPENSED' | 'NOT_DISPENSED' }) => recordDispensing(v.id, { status: v.status }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['pharmacy-given', patient.id] }),
    onError: (e) => Alert.alert('Could not record', e instanceof ApiError ? e.message : 'Check your connection.'),
  });
  const canRecord = can(me, 'prescription:dispense');
  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md }}>
      <Card>
        <Text style={{ color: t.text, fontSize: 18, fontWeight: '700' }}>{patient.full_name}</Text>
        <Text style={{ color: t.textMuted }}>{patient.mrn} · {patient.age_years ?? '?'} yrs</Text>
        <Button title="Choose a different patient" variant="secondary" onPress={onBack} />
      </Card>
      <Text style={{ color: t.textMuted }}>
        Pharmacists see signed prescriptions only. This is a read-only view for checking what the doctor prescribed; it records only whether the prescription was handed
        over, not brands, batches or stock, and it does not check interactions.
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
          {rx.status === 'SIGNED' ? (() => {
            const st = dispenseState((given.data ?? []).filter((d) => d.prescription_id === rx.id));
            return (
              <View style={{ gap: space.sm }}>
                <StatusChip label={st.label} tone={st.tone} />
                {canRecord && st.canRecord ? (
                  <View style={{ flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' }}>
                    <Button title="Dispensed" loading={record.isPending} onPress={() => record.mutate({ id: rx.id, status: 'DISPENSED' })} />
                    <Button title="Partly" variant="secondary" onPress={() => record.mutate({ id: rx.id, status: 'PARTIALLY_DISPENSED' })} />
                    <Button title="Not dispensed" variant="secondary" onPress={() => record.mutate({ id: rx.id, status: 'NOT_DISPENSED' })} />
                  </View>
                ) : null}
              </View>
            );
          })() : null}
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

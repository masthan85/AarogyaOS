import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';

import { getClinicalState, getEncounter, getPatient } from '@/api/endpoints';

/** Everything a clinical screen shows. PHI is kept in memory only while the screen is open. */
export function useEncounterData(encounterId: string) {
  const qc = useQueryClient();
  const detail = useQuery({ queryKey: ['encounter', encounterId], queryFn: () => getEncounter(encounterId), gcTime: 0 });
  const patientId = detail.data?.encounter.patient_id;
  const state = useQuery({
    queryKey: ['clinical-state', patientId],
    queryFn: () => getClinicalState(patientId as string),
    enabled: !!patientId,
    gcTime: 0,
  });
  const patient = useQuery({
    queryKey: ['patient', patientId],
    queryFn: () => getPatient(patientId as string),
    enabled: !!patientId,
    gcTime: 0,
  });
  const refresh = useCallback(async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ['encounter', encounterId] }),
      qc.invalidateQueries({ queryKey: ['clinical-state'] }),
    ]);
  }, [qc, encounterId]);
  return { detail: detail.data, state: state.data, patient: patient.data, refresh, isPending: detail.isPending, isError: detail.isError, retry: detail.refetch };
}
export type EncounterData = ReturnType<typeof useEncounterData>;

import { useQuery } from '@tanstack/react-query';

import { getFacilities, getPractitionersFull } from '@/api/endpoints';
import type { Letterhead } from '@/domain/print';

import type { EncounterData } from './useEncounterData';

/** Who is writing, where, and about whom: the top of a printed page. Null until all of it is known. */
export function useLetterhead(data: EncounterData): Letterhead | null {
  const facilities = useQuery({ queryKey: ['facilities'], queryFn: getFacilities });
  const practitioners = useQuery({ queryKey: ['practitioners-full'], queryFn: getPractitionersFull, gcTime: 0 });
  const enc = data.detail?.encounter;
  const p = data.patient;
  if (!enc || !p) return null;
  const facility = facilities.data?.find((f) => f.id === enc.facility_id);
  const doctor = practitioners.data?.find((x) => x.id === enc.practitioner_id);
  if (!facility || !doctor) return null;
  return {
    facility: facility.name,
    address: facility.address,
    doctor: `Dr ${doctor.full_name}`,
    registration: doctor.registration_number,
    patient: p.full_name,
    patientLine: `${p.age_years ?? '?'} years, ${p.administrative_gender}, MRN ${p.mrn}`,
  };
}

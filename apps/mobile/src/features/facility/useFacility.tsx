import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { getFacilities } from '@/api/endpoints';
import { ChoiceChips } from '@/design-system/components';

/** Selected facility for facility-scoped screens (queue, day view). Defaults to the first. */
export function useFacility() {
  const q = useQuery({ queryKey: ['facilities'], queryFn: getFacilities });
  const [chosen, setChosen] = useState<string>();
  const facilities = (q.data ?? []).filter((f) => f.status === 'ACTIVE');
  const facilityId = chosen ?? facilities[0]?.id;

  const picker =
    facilities.length > 1 ? (
      <ChoiceChips
        label="Facility"
        options={facilities.map((f) => ({ value: f.id, label: f.name }))}
        value={facilityId}
        onChange={setChosen}
      />
    ) : null;

  return { facilityId, picker, isPending: q.isPending, isError: q.isError, refetch: q.refetch };
}

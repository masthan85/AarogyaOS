import { useQuery } from '@tanstack/react-query';

import { getLanguages } from '@/api/endpoints';
import { LANGUAGE_OPTIONS } from '@/domain/languages';

/** Languages come from the server (data, not code). The bundled list is only an offline fallback. */
export function useLanguages(): { tag: string; label: string }[] {
  const q = useQuery({ queryKey: ['languages'], queryFn: getLanguages, staleTime: 60 * 60 * 1000, gcTime: 60 * 60 * 1000 });
  return q.data?.length ? q.data.map((l) => ({ tag: l.tag, label: l.native_name })) : LANGUAGE_OPTIONS;
}

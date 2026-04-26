import { useQuery } from '@tanstack/react-query';
import { papersApi } from '@/lib/api/papers';

export function usePaper(id: string | undefined) {
  return useQuery({
    queryKey: ['paper', id],
    queryFn: () => (id ? papersApi.getPaper(id) : Promise.reject('No ID')),
    enabled: !!id,
  });
}

export function usePaperOutput(id: string | undefined) {
  return useQuery({
    queryKey: ['paper-output', id],
    queryFn: () => (id ? papersApi.getOutputBundle(id) : Promise.reject('No ID')),
    enabled: !!id,
  });
}

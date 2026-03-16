import { useQuery } from '@tanstack/react-query'
import { useApiContext } from '../api/context'

export function useProviders() {
  const { client } = useApiContext()
  return useQuery({
    queryKey: ['providers'],
    queryFn: () => client!.getProviders(),
    enabled: !!client,
    staleTime: 60_000,
  })
}

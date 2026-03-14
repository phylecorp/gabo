import { useQuery } from '@tanstack/react-query'
import { useApiContext } from '../api/context'
import { SatClient } from '../api/client'

export function useProviders() {
  const { baseUrl } = useApiContext()
  return useQuery({
    queryKey: ['providers'],
    queryFn: () => new SatClient(baseUrl!).getProviders(),
    enabled: !!baseUrl,
    staleTime: 60_000,
  })
}

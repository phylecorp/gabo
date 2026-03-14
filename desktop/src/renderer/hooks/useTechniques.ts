import { useQuery } from '@tanstack/react-query'
import { useApiContext } from '../api/context'
import { SatClient } from '../api/client'

export function useTechniques() {
  const { baseUrl } = useApiContext()
  return useQuery({
    queryKey: ['techniques'],
    queryFn: () => new SatClient(baseUrl!).getTechniques(),
    enabled: !!baseUrl,
    staleTime: Infinity,
  })
}

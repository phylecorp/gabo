import { useQuery } from '@tanstack/react-query'
import { useApiContext } from '../api/context'

export function useTechniques() {
  const { client } = useApiContext()
  return useQuery({
    queryKey: ['techniques'],
    queryFn: () => client!.getTechniques(),
    enabled: !!client,
    staleTime: Infinity,
  })
}

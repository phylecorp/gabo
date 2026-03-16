/**
 * @decision DEC-DESKTOP-SETTINGS-HOOK-001
 * @title useSettings: React Query hook for settings CRUD with optimistic invalidation
 * @status accepted
 * @rationale Settings are read once on page load (staleTime: 0 forces a fresh
 *   fetch each visit so UI reflects any out-of-band env var changes). After a
 *   successful PUT we invalidate both 'settings' and 'providers' so the dashboard
 *   provider status strip updates without requiring a page reload.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useApiContext } from '../api/context'
import type { AppSettings } from '../api/types'

export function useSettings() {
  const { client } = useApiContext()
  return useQuery({
    queryKey: ['settings'],
    queryFn: () => client!.getSettings(),
    enabled: !!client,
    staleTime: 0, // Always re-fetch on mount — env vars may have changed
  })
}

export function useUpdateSettings() {
  const { client } = useApiContext()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (settings: AppSettings) =>
      client!.updateSettings(settings),
    onSuccess: () => {
      // Invalidate both settings and providers so dashboard status strip refreshes
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      queryClient.invalidateQueries({ queryKey: ['providers'] })
    },
  })
}

export function useTestProvider() {
  const { client } = useApiContext()

  return useMutation({
    mutationFn: (req: { provider: string; api_key: string; model?: string }) =>
      client!.testProvider(req),
  })
}

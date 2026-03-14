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
import { SatClient } from '../api/client'
import type { AppSettings } from '../api/types'

export function useSettings() {
  const { baseUrl } = useApiContext()
  return useQuery({
    queryKey: ['settings'],
    queryFn: () => new SatClient(baseUrl!).getSettings(),
    enabled: !!baseUrl,
    staleTime: 0, // Always re-fetch on mount — env vars may have changed
  })
}

export function useUpdateSettings() {
  const { baseUrl } = useApiContext()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (settings: AppSettings) =>
      new SatClient(baseUrl!).updateSettings(settings),
    onSuccess: () => {
      // Invalidate both settings and providers so dashboard status strip refreshes
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      queryClient.invalidateQueries({ queryKey: ['providers'] })
    },
  })
}

export function useTestProvider() {
  const { baseUrl } = useApiContext()

  return useMutation({
    mutationFn: (req: { provider: string; api_key: string; model?: string }) =>
      new SatClient(baseUrl!).testProvider(req),
  })
}

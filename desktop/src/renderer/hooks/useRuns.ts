/**
 * @decision DEC-DESKTOP-HOOKS-RUNS-001
 * @title useRuns / useRun / useDeleteRun — React Query wrappers for run list and lifecycle
 * @status accepted
 * @rationale Centralising all run-related server state here keeps components thin.
 *   useRuns polls every 10 s so the Dashboard stays fresh without a WebSocket.
 *   useDeleteRun invalidates the ['runs'] query on success so the list updates
 *   immediately after a delete without a manual refetch.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useApiContext } from '../api/context'
import { SatClient } from '../api/client'

export function useRuns(dir?: string, limit?: number) {
  const { baseUrl } = useApiContext()
  return useQuery({
    queryKey: ['runs', dir, limit],
    queryFn: () => new SatClient(baseUrl!).getRuns(dir, limit),
    enabled: !!baseUrl,
    refetchInterval: 10_000,
  })
}

export function useRun(runId: string | undefined) {
  const { baseUrl } = useApiContext()
  return useQuery({
    queryKey: ['run', runId],
    queryFn: () => new SatClient(baseUrl!).getRun(runId!),
    enabled: !!baseUrl && !!runId,
  })
}

export function useDeleteRun() {
  const { baseUrl } = useApiContext()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (runId: string) => new SatClient(baseUrl!).deleteRun(runId),
    onSuccess: () => {
      // Invalidate the runs list so Dashboard re-fetches immediately
      queryClient.invalidateQueries({ queryKey: ['runs'] })
    },
  })
}

export function useRenameRun() {
  const { baseUrl } = useApiContext()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ runId, name }: { runId: string; name: string }) =>
      new SatClient(baseUrl!).renameRun(runId, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['runs'] })
    },
  })
}

/**
 * Mutation hook to cancel a queued or running analysis run.
 * Invalidates the runs list on success so Dashboard updates immediately.
 */
export function useCancelRun() {
  const { baseUrl } = useApiContext()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (runId: string) => new SatClient(baseUrl!).cancelRun(runId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['runs'] })
    },
  })
}

/**
 * Query hook to get current concurrency status (running/queued counts).
 * Used by TopBar badge and NewAnalysis warning banner.
 * Polls every 5 seconds to stay reasonably fresh.
 */
export function useConcurrencyStatus() {
  const { baseUrl } = useApiContext()
  return useQuery({
    queryKey: ['concurrency'],
    queryFn: () => new SatClient(baseUrl!).getConcurrencyStatus(),
    enabled: !!baseUrl,
    refetchInterval: 5_000,
  })
}

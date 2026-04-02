/**
 * @decision DEC-DESKTOP-HOOKS-RUNS-001
 * @title useRuns / useRun / useDeleteRun — React Query wrappers for run list and lifecycle
 * @status accepted
 * @rationale Centralising all run-related server state here keeps components thin.
 *   useRuns polls every 10 s so the Dashboard stays fresh without a WebSocket.
 *   useDeleteRun invalidates the ['runs'] query on success so the list updates
 *   immediately after a delete without a manual refetch.
 *
 * @decision DEC-DESKTOP-HOOKS-RUNS-002
 * @title useRun — suppress retry on 404
 * @status accepted
 * @rationale The global QueryClient sets retry: 1, which causes a second 404 request
 *   when a run genuinely doesn't exist (e.g. after server restart). A 404 is a
 *   permanent not-found, not a transient error, so retrying it produces a duplicate
 *   log entry and wastes a network round-trip. The per-query retry function below
 *   overrides the global default: 404s fail immediately; all other errors (5xx,
 *   network timeouts) still get one retry from the caller.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useApiContext } from '../api/context'

export function useRuns(dir?: string, limit?: number) {
  const { client } = useApiContext()
  return useQuery({
    queryKey: ['runs', dir, limit],
    queryFn: () => client!.getRuns(dir, limit),
    enabled: !!client,
    refetchInterval: 10_000,
  })
}

export function useRun(runId: string | undefined) {
  const { client } = useApiContext()
  return useQuery({
    queryKey: ['run', runId],
    queryFn: () => client!.getRun(runId!),
    enabled: !!client && !!runId,
    // Don't retry 404s — a missing run won't reappear on retry.
    // All other errors (network issues, 5xx) still get one retry
    // consistent with the global QueryClient default (retry: 1).
    retry: (failureCount, error) => {
      if (error instanceof Error && error.message.includes('404')) return false
      return failureCount < 1
    },
  })
}

export function useDeleteRun() {
  const { client } = useApiContext()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (runId: string) => client!.deleteRun(runId),
    onSuccess: () => {
      // Invalidate the runs list so Dashboard re-fetches immediately
      queryClient.invalidateQueries({ queryKey: ['runs'] })
    },
  })
}

export function useRenameRun() {
  const { client } = useApiContext()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ runId, name }: { runId: string; name: string }) =>
      client!.renameRun(runId, name),
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
  const { client } = useApiContext()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (runId: string) => client!.cancelRun(runId),
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
  const { client } = useApiContext()
  return useQuery({
    queryKey: ['concurrency'],
    queryFn: () => client!.getConcurrencyStatus(),
    enabled: !!client,
    refetchInterval: 5_000,
  })
}

/**
 * @decision DEC-DESKTOP-MODELS-HOOK-001
 * @title useModels: React Query hook for provider model listings with lazy fetch
 * @status accepted
 * @rationale Model lists are fetched lazily — only when the component requests
 *   them for a provider that has (or may have) an API key. React Query handles
 *   caching and deduplication so multiple cards mounting simultaneously don't
 *   issue redundant requests. staleTime=5min is appropriate because the backend
 *   has its own 1-hour in-memory cache; the frontend cache prevents repeated
 *   calls during a single settings session while not outlasting the backend TTL.
 *   On error, the hook returns empty model lists so the caller can fall back to
 *   plain text input gracefully.
 */
import { useQuery } from '@tanstack/react-query'
import { useApiContext } from '../api/context'
import type { ProviderModels } from '../api/types'

const EMPTY_MODELS: ProviderModels = { analysis: [], research: [] }

/**
 * Fetch the available models for a provider from GET /api/config/models/{provider}.
 *
 * @param provider - provider name (e.g. "anthropic", "openai")
 * @param enabled  - set to false to skip the fetch (e.g. when no key is configured)
 *
 * Returns:
 * - models: ProviderModels with analysis/research arrays (empty on error/loading)
 * - isLoading: true while fetching
 * - error: Error object on failure (caller uses this to decide fallback rendering)
 */
export function useModels(provider: string, enabled = true) {
  const { client } = useApiContext()

  const { data, isLoading, error } = useQuery({
    queryKey: ['models', provider],
    queryFn: () => client!.getModels(provider),
    enabled: !!client && enabled,
    staleTime: 5 * 60 * 1000, // 5 minutes — backend caches for 1h
    retry: 1,
  })

  return {
    models: data?.models ?? EMPTY_MODELS,
    isLoading,
    error: error as Error | null,
  }
}

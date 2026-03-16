/**
 * @decision DEC-DESKTOP-HOOK-ANALYSIS-001
 * @title useAnalysis: useReducer-driven run progress state with WebSocket integration
 * @status accepted
 * @rationale Analysis run state has many fields that update in response to typed
 *   pipeline events. useReducer makes the state transitions explicit and testable —
 *   each event type maps to a deterministic state change. The reducer handles all
 *   14 event types from the Python EventBus. The hook owns the WebSocket lifecycle:
 *   connect on startAnalysis, disconnect on unmount. autoReconnect=false because
 *   analysis runs are one-shot and reconnecting produces duplicate/stale events.
 *
 * @decision DEC-AUTH-010
 * @title useAnalysis uses client from ApiContext to include auth token
 * @status accepted
 * @rationale SatClient is now constructed with the auth token in ApiProvider.
 *   useAnalysis reads client from ApiContext rather than constructing its own
 *   SatClient, ensuring the token flows through automatically. WebSocket URLs
 *   use client.buildWsUrl() to append ?token=<token>.
 */
import { useCallback, useEffect, useReducer, useRef } from 'react'
import { useApiContext } from '../api/context'
import { AnalysisWebSocket } from '../api/ws'
import type { AnalysisRequest, PipelineEventMessage, RunProgress } from '../api/types'

type Action =
  | { type: 'CONNECTING' }
  | { type: 'EVENT'; event: PipelineEventMessage }
  | { type: 'RESET' }

const initialState: RunProgress = {
  status: 'connecting',
  events: [],
  currentStage: null,
  currentTechnique: null,
  completedStages: [],
  researchProviders: {},
  error: null,
  outputDir: null,
}

function reducer(state: RunProgress, action: Action): RunProgress {
  switch (action.type) {
    case 'CONNECTING':
      return { ...initialState, status: 'connecting' }
    case 'RESET':
      return initialState
    case 'EVENT': {
      const { event } = action
      const newState = {
        ...state,
        status: 'running' as const,
        events: [...state.events, event],
      }

      switch (event.type) {
        case 'StageStarted':
          return { ...newState, currentStage: event.data.stage, currentTechnique: event.data.technique_id || null }
        case 'StageCompleted':
          return {
            ...newState,
            completedStages: [...state.completedStages, `${event.data.stage}:${event.data.technique_id}`],
            currentStage: null,
            currentTechnique: null,
          }
        case 'ResearchStarted':
          return {
            ...newState,
            currentStage: 'research',
            researchProviders: Object.fromEntries(
              (event.data.provider_names as string[]).map(n => [n, 'pending' as const])
            ),
          }
        case 'ProviderStarted':
          return {
            ...newState,
            researchProviders: { ...state.researchProviders, [event.data.name]: 'running' },
          }
        case 'ProviderCompleted':
          return {
            ...newState,
            researchProviders: { ...state.researchProviders, [event.data.name]: 'completed' },
          }
        case 'ProviderFailed':
          return {
            ...newState,
            researchProviders: { ...state.researchProviders, [event.data.name]: 'failed' },
          }
        case 'ResearchCompleted':
          return { ...newState, completedStages: [...state.completedStages, 'research'] }
        case 'run_completed':
          return { ...newState, status: 'completed', outputDir: event.data.output_dir }
        case 'run_failed':
          return { ...newState, status: 'failed', error: event.data.error }
        default:
          return newState
      }
    }
    default:
      return state
  }
}

export function useAnalysis() {
  const { wsBaseUrl, client } = useApiContext()
  const [progress, dispatch] = useReducer(reducer, initialState)
  const wsRef = useRef<AnalysisWebSocket | null>(null)

  const startAnalysis = useCallback(async (request: AnalysisRequest): Promise<string | null> => {
    if (!client || !wsBaseUrl) return null

    dispatch({ type: 'CONNECTING' })

    const response = await client.startAnalysis(request)

    // Connect WebSocket — append auth token as query parameter
    const rawWsUrl = `${wsBaseUrl}/ws/analysis/${response.run_id}`
    const wsUrl = client.buildWsUrl(rawWsUrl)
    const ws = new AnalysisWebSocket(wsUrl, false)
    wsRef.current = ws

    ws.onEvent((event) => {
      dispatch({ type: 'EVENT', event })
    })

    ws.connect()
    return response.run_id
  }, [client, wsBaseUrl])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      wsRef.current?.disconnect()
    }
  }, [])

  return { startAnalysis, progress, dispatch }
}

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
 */
import { useCallback, useEffect, useReducer, useRef } from 'react'
import { useApiContext } from '../api/context'
import { SatClient } from '../api/client'
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
  const { baseUrl, wsBaseUrl } = useApiContext()
  const [progress, dispatch] = useReducer(reducer, initialState)
  const wsRef = useRef<AnalysisWebSocket | null>(null)

  const startAnalysis = useCallback(async (request: AnalysisRequest): Promise<string | null> => {
    if (!baseUrl || !wsBaseUrl) return null

    dispatch({ type: 'CONNECTING' })

    const client = new SatClient(baseUrl)
    const response = await client.startAnalysis(request)

    // Connect WebSocket
    const wsUrl = `${wsBaseUrl}/ws/analysis/${response.run_id}`
    const ws = new AnalysisWebSocket(wsUrl, false)
    wsRef.current = ws

    ws.onEvent((event) => {
      dispatch({ type: 'EVENT', event })
    })

    ws.connect()
    return response.run_id
  }, [baseUrl, wsBaseUrl])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      wsRef.current?.disconnect()
    }
  }, [])

  return { startAnalysis, progress, dispatch }
}

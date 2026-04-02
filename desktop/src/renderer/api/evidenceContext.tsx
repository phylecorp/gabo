/**
 * EvidenceGatheringProvider — persistent evidence gathering state across navigation.
 *
 * State lives here (not in useEvidenceGathering hook / NewAnalysis component) so that
 * the WS connection and pool survive unmounts. The user can navigate away mid-gather
 * and return to see progress or results.
 *
 * @decision DEC-DESKTOP-HOOK-EVIDENCE-001
 * @title useEvidenceGathering: reducer-driven evidence gathering with WebSocket + local curation
 * @status accepted
 * @rationale Evidence gathering mirrors the analysis flow (POST → WS → events) but adds
 *   local curation state (toggling items). The reducer handles WS events identically to
 *   useAnalysis for research provider tracking, plus manages the EvidencePool and selection
 *   state. Selection mutations are local-only (no server round-trip needed).
 *   State now lives in EvidenceGatheringProvider (evidenceContext.tsx) so it persists
 *   across page navigation — the user can navigate away mid-gather and return to see results.
 *
 * @decision DEC-DESKTOP-HOOK-EVIDENCE-002
 * @title setPrebuiltPool: bypass WS gather flow for direct pool injection
 * @status accepted
 * @rationale When "Run Analysis" is clicked with evidence present, the frontend calls
 *   POST /api/evidence/pool which returns a pre-built EvidencePool synchronously (no WS).
 *   The SET_PREBUILT_POOL action injects that pool + sessionId directly into the reducer
 *   state (status=ready), so EvidenceReview renders immediately. The existing gather flow
 *   (WebSocket) is unchanged — this is an additive path for the "Run Analysis" button.
 *
 * @decision DEC-AUTH-011
 * @title evidenceContext uses client from ApiContext to include auth token
 * @status accepted
 * @rationale SatClient is constructed with the auth token in ApiProvider (DEC-AUTH-009).
 *   EvidenceGatheringProvider reads client from ApiContext rather than constructing its
 *   own SatClient, ensuring the token flows through all API calls. WebSocket URLs use
 *   client.buildWsUrl() to append ?token=<token> for WS auth.
 */
import { createContext, useContext, useCallback, useEffect, useReducer, useRef, type ReactNode } from 'react'
import { useApiContext } from './context'
import { AnalysisWebSocket } from './ws'
import type {
  EvidenceGatherRequest,
  EvidenceGatheringProgress,
  EvidenceItem,
  EvidencePool,
  PipelineEventMessage,
} from './types'

// ---------------------------------------------------------------------------
// State shape
// ---------------------------------------------------------------------------

interface EvidenceState {
  progress: EvidenceGatheringProgress
  pool: EvidencePool | null
  sessionId: string | null
}

// ---------------------------------------------------------------------------
// Action union
// ---------------------------------------------------------------------------

type Action =
  | { type: 'CONNECTING' }
  | { type: 'EVENT'; event: PipelineEventMessage }
  | { type: 'POOL_READY'; pool: EvidencePool }
  | { type: 'SET_PREBUILT_POOL'; pool: EvidencePool; sessionId: string }
  | { type: 'TOGGLE_ITEM'; itemId: string }
  | { type: 'UPDATE_ITEM'; itemId: string; updates: Partial<EvidenceItem> }
  | { type: 'ADD_ITEM'; item: EvidenceItem }
  | { type: 'SELECT_ALL' }
  | { type: 'DESELECT_ALL' }
  | { type: 'SELECT_BY_FILTER'; filter: 'high-confidence' | 'research' | 'decomposition' | 'user' }
  | { type: 'FAILED'; error: string }
  | { type: 'RESET' }
  | { type: 'SET_SESSION'; sessionId: string }

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------

const initialProgress: EvidenceGatheringProgress = {
  status: 'idle',
  events: [],
  researchProviders: {},
  error: null,
}

const initialState: EvidenceState = {
  progress: initialProgress,
  pool: null,
  sessionId: null,
}

// ---------------------------------------------------------------------------
// Helper functions
// ---------------------------------------------------------------------------

function updateProviders(
  providers: Record<string, 'pending' | 'running' | 'completed' | 'failed'>,
  name: string,
  status: 'pending' | 'running' | 'completed' | 'failed'
): Record<string, 'pending' | 'running' | 'completed' | 'failed'> {
  return { ...providers, [name]: status }
}

function mapItemsBy(
  items: EvidenceItem[],
  predicate: (item: EvidenceItem) => boolean,
  selected: boolean
): EvidenceItem[] {
  return items.map(item =>
    predicate(item) ? { ...item, selected } : item
  )
}

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

function reducer(state: EvidenceState, action: Action): EvidenceState {
  switch (action.type) {
    case 'CONNECTING':
      return {
        ...initialState,
        progress: { ...initialProgress, status: 'gathering' },
      }

    case 'SET_SESSION':
      return { ...state, sessionId: action.sessionId }

    case 'EVENT': {
      const { event } = action
      const newProgress: EvidenceGatheringProgress = {
        ...state.progress,
        status: 'gathering',
        events: [...state.progress.events, event],
      }

      switch (event.type) {
        case 'ResearchStarted':
          return {
            ...state,
            progress: {
              ...newProgress,
              researchProviders: Object.fromEntries(
                (event.data.provider_names as string[]).map(n => [n, 'pending' as const])
              ),
            },
          }
        case 'ProviderStarted':
          return {
            ...state,
            progress: {
              ...newProgress,
              researchProviders: updateProviders(state.progress.researchProviders, event.data.name, 'running'),
            },
          }
        case 'ProviderCompleted':
          return {
            ...state,
            progress: {
              ...newProgress,
              researchProviders: updateProviders(state.progress.researchProviders, event.data.name, 'completed'),
            },
          }
        case 'ProviderFailed':
          return {
            ...state,
            progress: {
              ...newProgress,
              researchProviders: updateProviders(state.progress.researchProviders, event.data.name, 'failed'),
            },
          }
        default:
          return { ...state, progress: newProgress }
      }
    }

    case 'POOL_READY':
      return {
        ...state,
        pool: action.pool,
        progress: { ...state.progress, status: 'ready' },
      }

    // Injected directly from POST /api/evidence/pool — no WS gather flow needed.
    case 'SET_PREBUILT_POOL':
      return {
        ...state,
        pool: action.pool,
        sessionId: action.sessionId,
        progress: { ...initialProgress, status: 'ready' },
      }

    case 'FAILED':
      return {
        ...state,
        progress: { ...state.progress, status: 'failed', error: action.error },
      }

    case 'TOGGLE_ITEM': {
      if (!state.pool) return state
      return {
        ...state,
        pool: {
          ...state.pool,
          items: state.pool.items.map(item =>
            item.item_id === action.itemId
              ? { ...item, selected: !item.selected }
              : item
          ),
        },
      }
    }

    case 'UPDATE_ITEM': {
      if (!state.pool) return state
      return {
        ...state,
        pool: {
          ...state.pool,
          items: state.pool.items.map(item =>
            item.item_id === action.itemId
              ? { ...item, ...action.updates }
              : item
          ),
        },
      }
    }

    case 'ADD_ITEM': {
      if (!state.pool) return state
      return {
        ...state,
        pool: {
          ...state.pool,
          items: [...state.pool.items, action.item],
        },
      }
    }

    case 'SELECT_ALL': {
      if (!state.pool) return state
      return {
        ...state,
        pool: {
          ...state.pool,
          items: mapItemsBy(state.pool.items, () => true, true),
        },
      }
    }

    case 'DESELECT_ALL': {
      if (!state.pool) return state
      return {
        ...state,
        pool: {
          ...state.pool,
          items: mapItemsBy(state.pool.items, () => true, false),
        },
      }
    }

    case 'SELECT_BY_FILTER': {
      if (!state.pool) return state
      const { filter } = action
      const filterFn = (item: EvidenceItem): boolean => {
        switch (filter) {
          case 'high-confidence':
            return item.confidence === 'High'
          case 'research':
            return item.source === 'research'
          case 'decomposition':
            return item.source === 'decomposition'
          case 'user':
            return item.source === 'user'
          default:
            return false
        }
      }
      return {
        ...state,
        pool: {
          ...state.pool,
          items: state.pool.items.map(item => ({ ...item, selected: filterFn(item) })),
        },
      }
    }

    case 'RESET':
      return initialState

    default:
      return state
  }
}

// ---------------------------------------------------------------------------
// Context value interface
// ---------------------------------------------------------------------------

interface EvidenceGatheringContextValue {
  gatherEvidence: (request: EvidenceGatherRequest) => Promise<void>
  /** Inject a pre-built pool (from POST /api/evidence/pool) directly, skipping the WS gather flow. */
  setPrebuiltPool: (pool: EvidencePool, sessionId: string) => void
  progress: EvidenceGatheringProgress
  evidencePool: EvidencePool | null
  sessionId: string | null
  toggleItem: (itemId: string) => void
  /** Update editable fields on a single evidence item via PATCH, then sync local state. */
  updateItem: (sessionId: string, itemId: string, updates: { claim?: string; confidence?: string; category?: string }) => Promise<void>
  /** Add a new user-authored evidence item via POST, then append to local pool state. */
  addItem: (sessionId: string, data: { claim: string; confidence?: string; category?: string }) => Promise<void>
  selectAll: () => void
  deselectAll: () => void
  selectByFilter: (filter: 'high-confidence' | 'research' | 'decomposition' | 'user' | 'document') => void
  selectedItems: EvidenceItem[]
  selectedCount: number
  totalCount: number
  reset: () => void
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const EvidenceGatheringContext = createContext<EvidenceGatheringContextValue | null>(null)

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function EvidenceGatheringProvider({ children }: { children: ReactNode }) {
  const { wsBaseUrl, client } = useApiContext()
  const [state, dispatch] = useReducer(reducer, initialState)
  const wsRef = useRef<AnalysisWebSocket | null>(null)
  const sessionIdRef = useRef<string | null>(null)

  const gatherEvidence = useCallback(async (request: EvidenceGatherRequest): Promise<void> => {
    if (!client || !wsBaseUrl) return

    dispatch({ type: 'CONNECTING' })

    const response = await client.gatherEvidence(request)

    sessionIdRef.current = response.session_id
    dispatch({ type: 'SET_SESSION', sessionId: response.session_id })

    // Connect WebSocket to evidence gathering stream — append auth token as query param
    const rawWsUrl = `${wsBaseUrl}/ws/evidence/${response.session_id}`
    const wsUrl = client.buildWsUrl(rawWsUrl)
    const ws = new AnalysisWebSocket(wsUrl, false)
    wsRef.current = ws

    ws.onEvent(async (event) => {
      dispatch({ type: 'EVENT', event })

      if (event.type === 'EvidenceGatheringCompleted') {
        // Fetch the full evidence pool now that gathering is done
        try {
          const pool = await client.getEvidencePool(response.session_id)
          dispatch({ type: 'POOL_READY', pool })
        } catch (err) {
          dispatch({
            type: 'FAILED',
            error: err instanceof Error ? err.message : 'Failed to fetch evidence pool',
          })
        }
      }
    })

    ws.connect()
  }, [client, wsBaseUrl])

  const toggleItem = useCallback((itemId: string) => {
    dispatch({ type: 'TOGGLE_ITEM', itemId })
  }, [])

  const selectAll = useCallback(() => {
    dispatch({ type: 'SELECT_ALL' })
  }, [])

  const deselectAll = useCallback(() => {
    dispatch({ type: 'DESELECT_ALL' })
  }, [])

  const selectByFilter = useCallback(
    (filter: 'high-confidence' | 'research' | 'decomposition' | 'user' | 'document') => {
      dispatch({ type: 'SELECT_BY_FILTER', filter })
    },
    []
  )

  const setPrebuiltPool = useCallback((pool: EvidencePool, sessionId: string) => {
    dispatch({ type: 'SET_PREBUILT_POOL', pool, sessionId })
  }, [])

  const updateItem = useCallback(async (
    sessionId: string,
    itemId: string,
    updates: { claim?: string; confidence?: string; category?: string },
  ) => {
    if (!client) return
    try {
      const updated = await client.updateEvidenceItem(sessionId, itemId, updates)
      dispatch({ type: 'UPDATE_ITEM', itemId, updates: updated })
    } catch (err) {
      console.error('Failed to update evidence item:', err)
    }
  }, [client])

  const addItem = useCallback(async (
    sessionId: string,
    data: { claim: string; confidence?: string; category?: string },
  ) => {
    if (!client) return
    try {
      const created = await client.createEvidenceItem(sessionId, data)
      dispatch({ type: 'ADD_ITEM', item: created })
    } catch (err) {
      console.error('Failed to create evidence item:', err)
    }
  }, [client])

  const reset = useCallback(() => {
    wsRef.current?.disconnect()
    wsRef.current = null
    sessionIdRef.current = null
    dispatch({ type: 'RESET' })
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      wsRef.current?.disconnect()
    }
  }, [])

  const selectedItems = state.pool?.items.filter(item => item.selected) ?? []
  const selectedCount = selectedItems.length
  const totalCount = state.pool?.items.length ?? 0

  const value: EvidenceGatheringContextValue = {
    gatherEvidence,
    setPrebuiltPool,
    progress: state.progress,
    evidencePool: state.pool,
    sessionId: state.sessionId,
    toggleItem,
    updateItem,
    addItem,
    selectAll,
    deselectAll,
    selectByFilter,
    selectedItems,
    selectedCount,
    totalCount,
    reset,
  }

  return (
    <EvidenceGatheringContext.Provider value={value}>
      {children}
    </EvidenceGatheringContext.Provider>
  )
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useEvidenceGathering(): EvidenceGatheringContextValue {
  const ctx = useContext(EvidenceGatheringContext)
  if (!ctx) {
    throw new Error('useEvidenceGathering must be used within an EvidenceGatheringProvider')
  }
  return ctx
}

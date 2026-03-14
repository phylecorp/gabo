/**
 * @decision DEC-DESKTOP-RUN-DETAIL-001
 * @title RunDetail: dual-mode page — live progress view or completed results view
 * @status accepted
 * @rationale A run can be in two states from the UI's perspective: actively
 *   running (user just navigated from NewAnalysis) or already complete (user
 *   navigated from Dashboard). For the live case, RunDetail connects its own
 *   WebSocket directly using the runId from the URL — this avoids coupling to
 *   NewAnalysis's hook instance, which would be unmounted by the time RunDetail
 *   mounts. The live flag is passed via location.state by NewAnalysis on navigate.
 *   For completed runs, only the REST API via useRun() is used.
 *   Artifact summaries are lazy-loaded per-technique when in results mode.
 *
 * @decision DEC-DESKTOP-RUN-DETAIL-002
 * @title Fix blinking/stuttering on navigation: batch summary loads, ref-guarded effects, memoized derived values
 * @status accepted
 * @rationale Three root causes produced N re-renders per navigation:
 *   1. forEach(async ...) fired N individual setSummaries calls (N = # techniques),
 *      causing N re-renders. Fixed with Promise.all + single setSummaries batch call.
 *   2. Synthesis effect had synthesis/synthLoading in its deps array — state changes
 *      caused re-evaluation creating a feedback loop. Fixed with synthLoadedRef to
 *      track load state outside React state, removing those deps.
 *   3. progress/stages recomputed every render. Fixed with useMemo.
 *   4. No AbortController cleanup — StrictMode double-mount caused stale updates.
 *      Fixed with AbortController + cleanup return in both effects.
 *   All useMemo/useRef/useEffect hooks are declared before any conditional returns
 *   to comply with React Rules of Hooks.
 *
 *   Wave 4 additions:
 *   - WebSocket auto-connects when run?.status === 'running' (Dashboard -> running run).
 *     isLiveSession kept for the pre-REST-load window when navigating from NewAnalysis.
 *   - Refresh button calls refetch() to pull latest REST data on demand.
 *   - Delete button (completed/failed only) calls useDeleteRun and navigates home.
 */
import { useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router'
import { useRun, useDeleteRun } from '../hooks/useRuns'
import ErrorState from '../components/common/ErrorState'
import { useToast } from '../components/common/Toast'
import { useApiContext } from '../api/context'
import { SatClient } from '../api/client'
import { AnalysisWebSocket } from '../api/ws'
import PipelineProgress, { type Stage } from '../components/progress/PipelineProgress'
import EventLog from '../components/progress/EventLog'
import StageCard from '../components/progress/StageCard'
import SynthesisPanel from '../components/results/SynthesisPanel'
import FindingsGrid from '../components/results/FindingsGrid'
import IntelBadge from '../components/common/IntelBadge'
import type {
  RunDetail as RunDetailType,
  SynthesisResult,
  Artifact,
  RunProgress,
  PipelineEventMessage,
} from '../api/types'

// ---- Progress reducer (mirrors useAnalysis.ts) ----

type Action =
  | { type: 'CONNECTING' }
  | { type: 'EVENT'; event: PipelineEventMessage }

const initialProgress: RunProgress = {
  status: 'connecting',
  events: [],
  currentStage: null,
  currentTechnique: null,
  completedStages: [],
  researchProviders: {},
  error: null,
  outputDir: null,
}

function progressReducer(state: RunProgress, action: Action): RunProgress {
  switch (action.type) {
    case 'CONNECTING':
      return { ...initialProgress, status: 'connecting' }
    case 'EVENT': {
      const { event } = action
      const next = {
        ...state,
        status: 'running' as const,
        events: [...state.events, event],
      }
      switch (event.type) {
        case 'StageStarted':
          return { ...next, currentStage: event.data.stage, currentTechnique: event.data.technique_id || null }
        case 'StageCompleted':
          return {
            ...next,
            completedStages: [...state.completedStages, `${event.data.stage}:${event.data.technique_id}`],
            currentStage: null,
            currentTechnique: null,
          }
        case 'ResearchStarted':
          return {
            ...next,
            currentStage: 'research',
            researchProviders: Object.fromEntries(
              (event.data.provider_names as string[]).map(n => [n, 'pending' as const])
            ),
          }
        case 'ProviderStarted':
          return { ...next, researchProviders: { ...state.researchProviders, [event.data.name]: 'running' } }
        case 'ProviderCompleted':
          return { ...next, researchProviders: { ...state.researchProviders, [event.data.name]: 'completed' } }
        case 'ProviderFailed':
          return { ...next, researchProviders: { ...state.researchProviders, [event.data.name]: 'failed' } }
        case 'ResearchCompleted':
          return { ...next, completedStages: [...state.completedStages, 'research'] }
        case 'run_completed':
          return { ...next, status: 'completed', outputDir: event.data.output_dir }
        case 'run_failed':
          return { ...next, status: 'failed', error: event.data.error }
        default:
          return next
      }
    }
    default:
      return state
  }
}

// ---- helpers ----

function statusBadgeClass(status: string): string {
  if (status === 'running' || status === 'connecting') return 'badge-cyan'
  if (status === 'completed') return 'badge-green'
  return 'badge-red'
}

function buildStages(run: RunDetailType, hasResearch: boolean): Stage[] {
  const stages: Stage[] = []
  if (hasResearch) {
    stages.push({ id: 'research', label: 'Research', kind: 'research' })
  }
  for (const techId of run.techniques_selected) {
    const artifact = run.artifacts.find(a => a.technique_id === techId)
    stages.push({
      id: techId,
      label: artifact?.technique_name ?? techId,
      kind: 'technique',
    })
  }
  stages.push({ id: 'synthesis', label: 'Synthesis', kind: 'synthesis' })
  return stages
}

function makeCompletedProgress(run: RunDetailType): RunProgress {
  return {
    status: run.status === 'completed' ? 'completed' : run.status === 'failed' ? 'failed' : 'running',
    events: [],
    currentStage: null,
    currentTechnique: null,
    completedStages: run.techniques_completed.map(id => `analysis:${id}`),
    researchProviders: {},
    error: null,
    outputDir: null,
  }
}

// ---- Main component ----

export default function RunDetail() {
  const { runId } = useParams<{ runId: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const { baseUrl, wsBaseUrl } = useApiContext()

  // Detect live session (navigated from NewAnalysis)
  const isLiveSession = Boolean((location.state as Record<string, unknown>)?.liveSession)

  // REST data
  const { data: run, isLoading, error: runError, refetch } = useRun(runId)

  // Local live progress state (only used when connected via WebSocket)
  const [liveProgress, dispatch] = useReducer(progressReducer, initialProgress)
  const [wsConnected, setWsConnected] = useState(false)
  const [wsDisconnected, setWsDisconnected] = useState(false)

  // Delete hook — used for completed/failed runs
  const deleteRun = useDeleteRun()
  const { addToast } = useToast()

  // Report availability state: null = unknown, true = exists, false = missing
  const [reportExists, setReportExists] = useState<boolean | null>(null)
  const [reportGenerating, setReportGenerating] = useState(false)

  // Connect WebSocket when this is a live session (navigated from NewAnalysis)
  // OR when the REST data shows the run is still running (navigated from Dashboard).
  // isLiveSession handles the initial render before REST data arrives.
  useEffect(() => {
    const shouldConnect = isLiveSession || run?.status === 'running'
    if (!shouldConnect || !wsBaseUrl || !runId) return
    dispatch({ type: 'CONNECTING' })
    setWsConnected(true)
    setWsDisconnected(false)
    const ws = new AnalysisWebSocket(`${wsBaseUrl}/ws/analysis/${runId}`, false)
    ws.onEvent(event => dispatch({ type: 'EVENT', event }))
    ws.onDisconnect(() => setWsDisconnected(true))
    ws.connect()
    return () => { ws.disconnect(); setWsConnected(false) }
  }, [isLiveSession, run?.status, wsBaseUrl, runId])

  // True when we have an active WebSocket feeding live events
  const isLive = isLiveSession || wsConnected

  // Synthesis data (lazy-loaded when run completes)
  const [synthesis, setSynthesis] = useState<SynthesisResult | null>(null)
  const [synthLoading, setSynthLoading] = useState(false)

  // Summaries per technique (lazy-loaded)
  const [summaries, setSummaries] = useState<Record<string, string>>({})

  // Effective status
  const liveStatus = isLive ? liveProgress.status : null
  const effectiveStatus = liveStatus ?? run?.status ?? 'loading'

  // Refetch REST data when live run completes/fails
  useEffect(() => {
    if (liveStatus === 'completed' || liveStatus === 'failed') {
      refetch()
    }
  }, [liveStatus, refetch])

  // Load synthesis — ref-guarded to prevent feedback loop from synthesis/synthLoading
  // being in the deps array. AbortController prevents stale updates on StrictMode
  // double-mount. Uses granular deps (run_id, status, synthesis_path) instead of
  // the entire run object to avoid re-firing on unrelated run field changes.
  const synthLoadedRef = useRef(false)

  useEffect(() => {
    if (!run || !baseUrl || !run.synthesis_path) return
    if (run.status !== 'completed') return
    if (synthLoadedRef.current) return

    synthLoadedRef.current = true
    const controller = new AbortController()
    setSynthLoading(true)
    new SatClient(baseUrl)
      .getRunArtifact(run.run_id, run.synthesis_path)
      .then(data => {
        if (!controller.signal.aborted) setSynthesis(data as SynthesisResult)
      })
      .catch(() => {})
      .finally(() => {
        if (!controller.signal.aborted) setSynthLoading(false)
      })
    return () => controller.abort()
  }, [run?.run_id, run?.status, run?.synthesis_path, baseUrl])

  // Load technique summaries — batched via Promise.all to produce a single
  // setSummaries call (vs N calls from forEach(async)), eliminating N re-renders.
  // loadedSummariesRef tracks in-flight technique IDs outside React state to
  // prevent re-entry without adding summaries to the deps array.
  const loadedSummariesRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    if (!run || !baseUrl) return
    const pending = run.artifacts.filter(
      (a: Artifact) => a.json_path && !loadedSummariesRef.current.has(a.technique_id)
    )
    if (pending.length === 0) return

    // Mark as loading to prevent re-entry
    pending.forEach(a => loadedSummariesRef.current.add(a.technique_id))

    const controller = new AbortController()
    const client = new SatClient(baseUrl)

    Promise.all(
      pending.map(async (artifact: Artifact) => {
        if (!artifact.json_path) return null
        try {
          const data = await client.getRunArtifact(run.run_id, artifact.json_path)
          return data?.summary ? { id: artifact.technique_id, summary: String(data.summary) } : null
        } catch {
          return null
        }
      })
    ).then(results => {
      if (controller.signal.aborted) return
      const batch: Record<string, string> = {}
      for (const r of results) {
        if (r) batch[r.id] = r.summary
      }
      if (Object.keys(batch).length > 0) {
        setSummaries(prev => ({ ...prev, ...batch }))
      }
    })

    return () => controller.abort()
  }, [run?.run_id, run?.artifacts.length, baseUrl])

  // Check whether a report already exists for this run.
  // Fires once when the run reaches completed status and baseUrl is available.
  // Uses getRunReport (html) — a 404 means no report yet, any other response means it exists.
  useEffect(() => {
    if (!run || run.status !== 'completed' || !baseUrl || reportExists !== null) return
    const client = new SatClient(baseUrl)
    client.getRunReport(run.run_id, 'html')
      .then(() => setReportExists(true))
      .catch(() => setReportExists(false))
  }, [run?.run_id, run?.status, baseUrl, reportExists])

  async function handleGenerateReport() {
    if (!run || !baseUrl) return
    setReportGenerating(true)
    try {
      await new SatClient(baseUrl).generateReport(run.run_id)
      setReportExists(true)
    } catch (err: unknown) {
      addToast(`Report generation failed: ${(err as Error).message}`, 'error')
    } finally {
      setReportGenerating(false)
    }
  }

  // Memoize derived values — computed every render without memoization was
  // a source of wasted work on every state update (including the N summary loads).
  const isRunning = effectiveStatus === 'running' || effectiveStatus === 'connecting'
  const isComplete = effectiveStatus === 'completed'
  const isFailed = effectiveStatus === 'failed'

  const hasResearch = isLiveSession
    ? Object.keys(liveProgress.researchProviders).length > 0
    : (run?.artifacts.some(a => a.technique_id === 'research') ?? false)

  const progress = useMemo(
    () => isLiveSession ? liveProgress : (run ? makeCompletedProgress(run) : initialProgress),
    [isLiveSession, liveProgress, run]
  )

  const stages: Stage[] = useMemo(
    () => run ? buildStages(run, hasResearch) : [],
    [run, hasResearch]
  )

  // Conditional returns AFTER all hooks (Rules of Hooks compliance)
  if (isLoading && !run) {
    return (
      <div className="run-detail-loading">
        <span className="text-secondary text-sm">Loading run...</span>
      </div>
    )
  }

  if (!run && !isLiveSession) {
    const is404 = runError && (runError as Error).message?.includes('404')
    return (
      <ErrorState
        title={is404 ? 'Run Not Found' : 'Failed to Load Run'}
        message={is404
          ? `No analysis found with ID ${runId}`
          : `Could not load run: ${(runError as Error)?.message ?? 'Unknown error'}`
        }
        onRetry={!is404 ? () => refetch() : undefined}
        onBack={() => navigate('/')}
        backLabel="← Back to Dashboard"
      />
    )
  }

  return (
    <div className="run-detail">
      {/* Header */}
      <div className="run-detail-header">
        <div className="run-detail-header-left">
          <button
            className="run-detail-back text-muted text-xs"
            onClick={() => navigate('/')}
            type="button"
          >
            ← Dashboard
          </button>
          <h2 className="run-detail-question">
            {run?.question ?? 'Analysis in progress...'}
          </h2>
          {run && (
            <span className="run-detail-id font-mono text-xs text-muted">
              {run.run_id}
            </span>
          )}
        </div>
        <div className="run-detail-header-right">
          <span className={`intel-badge ${statusBadgeClass(effectiveStatus)}`}>
            {effectiveStatus}
          </span>
          {run?.adversarial_enabled && (
            <IntelBadge label="adversarial" variant="default" />
          )}
          {run?.evidence_provided && (
            <IntelBadge label="evidence" variant="default" />
          )}
          <button
            type="button"
            className="btn-secondary"
            title="Refresh run data"
            onClick={() => refetch()}
          >
            ↻
          </button>
          {isComplete && run && (
            <>
              {reportExists === true && (
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => navigate(`/runs/${run.run_id}/report`)}
                >
                  View Report
                </button>
              )}
              {reportExists === false && (
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={reportGenerating}
                  onClick={handleGenerateReport}
                >
                  {reportGenerating ? 'Generating...' : 'Generate Report'}
                </button>
              )}
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  if (!baseUrl) return
                  new SatClient(baseUrl).downloadExport(run.run_id).then(blob => {
                    const url = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = url
                    a.download = `sat-${run.run_id}.zip`
                    a.click()
                    URL.revokeObjectURL(url)
                  })
                }}
              >
                Export All
              </button>
            </>
          )}
          {isFailed && run && (
            <button
              type="button"
              className="btn-retry"
              onClick={() => navigate('/new', { state: { prefill: {
                question: run.question,
                techniques: run.techniques_selected,
                adversarialEnabled: run.adversarial_enabled,
              }}})}
            >
              Re-run Analysis
            </button>
          )}
          {(isComplete || isFailed) && run && (
            <button
              type="button"
              className="btn-secondary btn-danger"
              onClick={() => {
                if (window.confirm(`Delete run ${run.run_id}? This cannot be undone.`)) {
                  deleteRun.mutate(run.run_id, {
                    onSuccess: () => navigate('/'),
                    onError: (err) => addToast(`Delete failed: ${(err as Error).message}`, 'error'),
                  })
                }
              }}
            >
              Delete
            </button>
          )}
        </div>
      </div>

      {/* Pipeline progress */}
      {stages.length > 0 && (
        <div className="run-detail-pipeline">
          <PipelineProgress stages={stages} progress={progress} />
        </div>
      )}

      {/* WS disconnect banner */}
      {wsDisconnected && isLive && isRunning && (
        <div className="ws-disconnect-banner">
          <span>Live updates disconnected — data may be stale.</span>
          <button onClick={() => refetch()}>Refresh</button>
        </div>
      )}

      {/* Live progress section */}
      {isLive && (isRunning || isFailed) && (
        <div className="run-detail-live">
          {(liveProgress.currentTechnique || liveProgress.currentStage) && (
            <StageCard
              techniqueName={liveProgress.currentTechnique ?? liveProgress.currentStage ?? ''}
              stageName={liveProgress.currentStage ?? undefined}
            />
          )}

          {Object.keys(liveProgress.researchProviders).length > 0 && (
            <div className="run-detail-research-providers">
              <span className="run-detail-section-label text-xs text-muted">
                RESEARCH PROVIDERS
              </span>
              <div className="flex gap-2" style={{ flexWrap: 'wrap', marginTop: 6 }}>
                {Object.entries(liveProgress.researchProviders).map(([name, pStatus]) => (
                  <div key={name} className="provider-status-item">
                    <span className={`status-dot status-dot-${pStatus === 'completed' ? 'ok' : pStatus === 'failed' ? 'error' : 'warn'}`} />
                    <span className="text-xs text-secondary">{name}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {isFailed && liveProgress.error && (
            <div className="run-detail-error-panel">
              <span className="intel-badge badge-red">FAILED</span>
              <span className="text-sm text-secondary">{liveProgress.error}</span>
            </div>
          )}

          <EventLog events={liveProgress.events} />
        </div>
      )}

      {/* Results section */}
      {isComplete && run && (
        <div className="run-detail-results">
          {synthLoading && (
            <div className="run-detail-synth-loading">
              <span className="text-muted text-sm">Loading synthesis...</span>
            </div>
          )}
          {synthesis && !synthLoading && (
            <div className="run-detail-section">
              <div className="run-detail-section-header">
                <span className="run-detail-section-title">Synthesis</span>
              </div>
              <SynthesisPanel synthesis={synthesis} />
            </div>
          )}

          {run.artifacts.length > 0 && (
            <div className="run-detail-section">
              <div className="run-detail-section-header">
                <span className="run-detail-section-title">Technique Results</span>
                <span className="text-muted text-xs">
                  {run.techniques_completed.length} of {run.techniques_selected.length} completed
                </span>
              </div>
              <FindingsGrid
                artifacts={run.artifacts}
                runId={run.run_id}
                summaries={summaries}
              />
            </div>
          )}

          <div className="run-detail-section run-detail-meta-section">
            <div className="run-detail-meta-grid">
              <div className="run-detail-meta-item">
                <span className="run-detail-meta-label">Started</span>
                <span className="run-detail-meta-value font-mono text-xs">
                  {new Date(run.started_at).toLocaleString()}
                </span>
              </div>
              {run.completed_at && (
                <div className="run-detail-meta-item">
                  <span className="run-detail-meta-label">Completed</span>
                  <span className="run-detail-meta-value font-mono text-xs">
                    {new Date(run.completed_at).toLocaleString()}
                  </span>
                </div>
              )}
              {run.providers_used.length > 0 && (
                <div className="run-detail-meta-item">
                  <span className="run-detail-meta-label">Providers Used</span>
                  <span className="run-detail-meta-value font-mono text-xs">
                    {run.providers_used.join(', ')}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * @decision DEC-DESKTOP-DASHBOARD-001
 * @title Dashboard: recent-runs grid with provider status and quick launch
 * @status accepted
 * @rationale The dashboard is the analyst's home base. Recent runs grid gives
 *   immediate re-entry into prior work. Provider status shows whether the system
 *   is ready to run a new analysis before the analyst tries. The quick-launch
 *   CTA is prominent so the most common action (start new analysis) requires
 *   minimal navigation. Empty state educates new users rather than showing
 *   a blank screen.
 *   Delete buttons on run cards let analysts prune stale runs without leaving
 *   the dashboard. A manual refresh button sits next to the CTA for when the
 *   10 s poll hasn't fired yet.
 */
import { useState, useRef, useEffect } from 'react'
import { Link, useNavigate } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { useRuns, useDeleteRun, useCancelRun, useRenameRun } from '../hooks/useRuns'
import { useProviders } from '../hooks/useProviders'
import IntelCard from '../components/common/IntelCard'
import ErrorState from '../components/common/ErrorState'
import { useToast } from '../components/common/Toast'
import Welcome from '../components/Welcome'

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const secs = Math.floor(diff / 1000)
  if (secs < 60) return `${secs}s ago`
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function statusAccent(status: string): 'cyan' | 'green' | 'red' | 'amber' {
  if (status === 'running') return 'cyan'
  if (status === 'completed') return 'green'
  if (status === 'queued') return 'amber'
  return 'red'
}

function statusBadgeClass(status: string): string {
  if (status === 'running') return 'badge-cyan'
  if (status === 'completed') return 'badge-green'
  if (status === 'queued') return 'badge-amber'
  return 'badge-red'
}

export default function Dashboard() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: runs, isLoading: runsLoading, error: runsError, refetch: refetchRuns } = useRuns(undefined, 20)
  const { data: providers } = useProviders()
  const deleteRun = useDeleteRun()
  const cancelRun = useCancelRun()
  const renameRun = useRenameRun()
  const { addToast } = useToast()

  // Inline rename state: which run is being edited and the draft value
  const [editingRunId, setEditingRunId] = useState<string | null>(null)
  const [editingName, setEditingName] = useState('')
  const editInputRef = useRef<HTMLInputElement>(null)

  // Focus the input whenever a rename starts
  useEffect(() => {
    if (editingRunId && editInputRef.current) {
      editInputRef.current.focus()
      editInputRef.current.select()
    }
  }, [editingRunId])

  function startRename(runId: string, currentName: string | null | undefined, question: string) {
    setEditingRunId(runId)
    setEditingName(currentName ?? '')
  }

  function commitRename(runId: string) {
    const trimmed = editingName.trim()
    setEditingRunId(null)
    if (trimmed === '') return
    renameRun.mutate(
      { runId, name: trimmed },
      { onError: (err) => addToast(`Rename failed: ${(err as Error).message}`, 'error') }
    )
  }

  function cancelRename() {
    setEditingRunId(null)
    setEditingName('')
  }

  const activeProviders = providers?.filter(p => p.has_api_key) ?? []
  const hasProviders = activeProviders.length > 0

  return (
    <div className="dashboard">
      {/* Header row */}
      <div className="dashboard-header">
        <div className="dashboard-header-left">
          <h2 className="dashboard-title">Recent Analyses</h2>
          <span className="dashboard-subtitle text-muted text-xs">
            Structured analytic techniques for intelligence analysis
          </span>
        </div>
        <div className="dashboard-header-actions">
          <button
            className="btn-secondary"
            title="Refresh list"
            onClick={() => queryClient.invalidateQueries({ queryKey: ['runs'] })}
          >
            ↻
          </button>
          <button
            className="btn-primary"
            onClick={() => navigate('/new')}
          >
            + New Analysis
          </button>
        </div>
      </div>

      {/* System status strip */}
      {providers && providers.length > 0 && (
        <div className="dashboard-status-strip">
          <span className="dashboard-status-label text-xs text-muted">PROVIDERS</span>
          <div className="dashboard-status-providers">
            {providers.map(p => (
              <div key={p.name} className="dashboard-status-provider">
                <span className={`status-dot ${p.has_api_key ? 'status-dot-ok' : 'status-dot-error'}`} />
                <span className="text-xs text-secondary">{p.name}</span>
                {!p.has_api_key && (
                  <span className="text-xs text-muted">(no key)</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Runs grid */}
      {runsError && !runsLoading && (
        <ErrorState
          message={`Failed to load analyses: ${(runsError as Error).message}`}
          onRetry={() => refetchRuns()}
        />
      )}

      {runsLoading && (
        <div className="dashboard-loading">
          <span className="text-secondary text-sm">Loading analyses...</span>
        </div>
      )}

      {!runsLoading && (!runs || runs.length === 0) && (
        <Welcome hasProviders={hasProviders} />
      )}

      {runs && runs.length > 0 && (
        <div className="dashboard-grid">
          {runs.map(run => (
            <div key={run.run_id} className="run-card-wrapper">
              <Link to={`/runs/${run.run_id}`} className="run-card-link">
                <IntelCard accent={statusAccent(run.status)}>
                  {editingRunId === run.run_id ? (
                    <input
                      ref={editInputRef}
                      type="text"
                      className="run-card-rename-input"
                      value={editingName}
                      maxLength={100}
                      onChange={e => setEditingName(e.target.value)}
                      onBlur={() => commitRename(run.run_id)}
                      onKeyDown={e => {
                        if (e.key === 'Enter') { e.preventDefault(); commitRename(run.run_id) }
                        if (e.key === 'Escape') { e.preventDefault(); cancelRename() }
                      }}
                      onClick={e => { e.preventDefault(); e.stopPropagation() }}
                    />
                  ) : run.name ? (
                    <div
                      className="run-card-name"
                      title="Click to rename"
                      onClick={e => { e.preventDefault(); e.stopPropagation(); startRename(run.run_id, run.name, run.question) }}
                    >
                      {run.name}
                    </div>
                  ) : (
                    <div
                      className="run-card-question"
                      title="Click to add a name"
                      onClick={e => { e.preventDefault(); e.stopPropagation(); startRename(run.run_id, run.name, run.question) }}
                    >
                      {run.question.length > 80 ? run.question.slice(0, 77) + '...' : run.question}
                    </div>
                  )}
                  {run.name && (
                    <div className="run-card-question text-sm text-muted">
                      {run.question.length > 80 ? run.question.slice(0, 77) + '...' : run.question}
                    </div>
                  )}
                  <div className="run-card-id font-mono text-xs text-muted">{run.run_id}</div>
                  <div className="run-card-meta">
                    <span className={`intel-badge ${statusBadgeClass(run.status)}`}>
                      {run.status}
                    </span>
                    <span className="text-muted text-xs">
                      {run.techniques_completed.length}/{run.techniques_selected.length} techniques
                    </span>
                    <span className="run-card-time text-muted text-xs">
                      {run.status === 'running'
                        ? 'In progress'
                        : run.status === 'queued'
                        ? 'Waiting...'
                        : run.started_at
                        ? relativeTime(run.started_at)
                        : ''}
                    </span>
                  </div>
                  {run.evidence_provided && (
                    <button
                      type="button"
                      className="intel-badge badge-default mt-6"
                      style={{ cursor: 'pointer', background: 'none', border: '1px solid var(--color-border-subtle)', borderRadius: 4 }}
                      title="View evidence pool"
                      onClick={e => {
                        e.preventDefault()
                        e.stopPropagation()
                        navigate(`/runs/${run.run_id}/evidence`)
                      }}
                    >
                      evidence
                    </button>
                  )}
                </IntelCard>
              </Link>
              {run.status === 'queued' && (
                <button
                  type="button"
                  className="run-card-cancel"
                  title="Cancel this queued run"
                  onClick={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                    cancelRun.mutate(run.run_id, {
                      onError: (err) => addToast(`Cancel failed: ${(err as Error).message}`, 'error'),
                    })
                  }}
                >
                  ✕
                </button>
              )}
              {run.status !== 'running' && run.status !== 'queued' && (
                <button
                  type="button"
                  className="run-card-delete"
                  title="Delete this run"
                  onClick={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                    if (window.confirm(`Delete run ${run.run_id}? This cannot be undone.`)) {
                      deleteRun.mutate(run.run_id, {
                        onError: (err) => addToast(`Delete failed: ${(err as Error).message}`, 'error'),
                      })
                    }
                  }}
                >
                  ×
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

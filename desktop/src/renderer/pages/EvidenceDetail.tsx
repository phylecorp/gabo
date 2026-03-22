/**
 * @decision DEC-DESKTOP-EVIDENCE-DETAIL-001
 * @title EvidenceDetail: read-only page displaying persisted EvidencePool for a completed run
 * @status accepted
 * @rationale Analysts need to inspect what evidence was actually used in a curated analysis
 *   run — not to modify it (that happens at gather time), but to audit the pool post-hoc.
 *   The page fetches GET /api/runs/{runId}/evidence and renders items, sources, and gaps in
 *   the same visual style as EvidenceReview but without interactive controls (checkboxes,
 *   select-all buttons). Evidence items display source, confidence, category, verified status,
 *   and provider name, matching the fields from EvidencePool/EvidenceItem models exactly.
 *   Returns 404-aware graceful empty state when the run has no evidence.json.
 */
import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router'
import { useRun } from '../hooks/useRuns'
import { useApiContext } from '../api/context'
import type { EvidencePool } from '../api/types'

export default function EvidenceDetail() {
  const { runId } = useParams<{ runId: string }>()
  const navigate = useNavigate()
  const { baseUrl, client } = useApiContext()

  const { data: run, isLoading: runLoading } = useRun(runId)
  const [pool, setPool] = useState<EvidencePool | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!runId || !baseUrl || !client) return
    setLoading(true)
    setError(null)
    client.getRunEvidence(runId)
      .then(data => {
        setPool(data)
        setLoading(false)
      })
      .catch(err => {
        setError((err as Error).message ?? 'Failed to load evidence')
        setLoading(false)
      })
  }, [runId, baseUrl, client])

  const question = pool?.question ?? run?.question ?? 'Analysis'

  if (loading || runLoading) {
    return (
      <div className="run-detail-loading">
        <span className="text-secondary text-sm">Loading evidence...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="run-detail">
        <div className="run-detail-header">
          <div className="run-detail-header-left">
            <button
              className="run-detail-back text-muted text-xs"
              onClick={() => navigate(`/runs/${runId}`)}
              type="button"
            >
              {'\u2190'} Back to Run
            </button>
            <h2 className="run-detail-question">Evidence</h2>
          </div>
        </div>
        <div className="run-detail-results">
          <div className="run-detail-section">
            <span className="text-secondary text-sm">Error loading evidence: {error}</span>
          </div>
        </div>
      </div>
    )
  }

  if (!pool) {
    return (
      <div className="run-detail">
        <div className="run-detail-header">
          <div className="run-detail-header-left">
            <button
              className="run-detail-back text-muted text-xs"
              onClick={() => navigate(`/runs/${runId}`)}
              type="button"
            >
              {'\u2190'} Back to Run
            </button>
            <h2 className="run-detail-question">Evidence</h2>
          </div>
        </div>
        <div className="run-detail-results">
          <div className="run-detail-section">
            <span className="text-secondary text-sm">No evidence data available for this run.</span>
          </div>
        </div>
      </div>
    )
  }

  const itemCount = pool.items.length
  const sourceCount = pool.sources?.length ?? 0
  const gapCount = pool.gaps?.length ?? 0

  return (
    <div className="run-detail">
      {/* Header */}
      <div className="run-detail-header">
        <div className="run-detail-header-left">
          <button
            className="run-detail-back text-muted text-xs"
            onClick={() => navigate(`/runs/${runId}`)}
            type="button"
          >
            {'\u2190'} Back to Run
          </button>
          <h2 className="run-detail-question">
            Evidence for: {question}
          </h2>
          {pool.session_id && (
            <span className="run-detail-id font-mono text-xs text-muted">
              session: {pool.session_id}
            </span>
          )}
        </div>
        <div className="run-detail-header-right">
          <span className={`intel-badge ${pool.status === 'ready' ? 'badge-green' : pool.status === 'failed' ? 'badge-red' : 'badge-cyan'}`}>
            {pool.status}
          </span>
        </div>
      </div>

      {/* Stats bar */}
      <div className="evidence-summary-bar">
        <span className="evidence-summary-count">
          <strong>{itemCount}</strong> item{itemCount !== 1 ? 's' : ''} from{' '}
          <strong>{sourceCount}</strong> source{sourceCount !== 1 ? 's' : ''}
          {gapCount > 0 && (
            <> &mdash; <strong>{gapCount}</strong> gap{gapCount !== 1 ? 's' : ''} identified</>
          )}
        </span>
        {pool.provider_summary && (
          <span className="text-muted text-xs">{pool.provider_summary}</span>
        )}
      </div>

      {/* Evidence Items section */}
      {pool.items.length > 0 && (
        <div className="run-detail-section">
          <div className="run-detail-section-header">
            <span className="run-detail-section-title">Evidence Items</span>
            <span className="text-muted text-xs">{itemCount} total</span>
          </div>
          <div className="evidence-items" style={{ maxHeight: 'none' }}>
            {pool.items.map(item => (
              <div
                key={item.item_id}
                className={`evidence-item${item.selected ? '' : ' deselected'}`}
                style={{ cursor: 'default' }}
              >
                <div className="evidence-item-content">
                  <div className="evidence-item-claim">{item.claim}</div>
                  <div className="evidence-item-meta">
                    {/* Source badge */}
                    <span className={`evidence-badge evidence-badge-source-${item.source}`}>
                      {item.source}
                    </span>

                    {/* Provider name (research items only) */}
                    {item.provider_name && (
                      <span className="evidence-badge evidence-badge-provider">
                        {item.provider_name}
                      </span>
                    )}

                    {/* Confidence badge */}
                    <span className={`evidence-badge evidence-badge-confidence-${item.confidence}`}>
                      {item.confidence}
                    </span>

                    {/* Category badge */}
                    {item.category && (
                      <span
                        className="evidence-badge"
                        style={{ background: 'rgba(152,152,176,0.1)', color: 'var(--color-text-secondary)' }}
                      >
                        {item.category}
                      </span>
                    )}

                    {/* Verified indicator */}
                    {item.verified && (
                      <span className="evidence-badge evidence-badge-verified" title="Verified">
                        {'\u2713'} verified
                      </span>
                    )}

                    {/* Selection status */}
                    {!item.selected && (
                      <span
                        className="evidence-badge"
                        style={{ background: 'rgba(244,63,94,0.1)', color: 'var(--color-signal-red)' }}
                        title="Not selected for analysis"
                      >
                        excluded
                      </span>
                    )}
                  </div>

                  {/* Entities */}
                  {item.entities && item.entities.length > 0 && (
                    <div className="text-xs text-muted" style={{ marginTop: 4 }}>
                      Entities: {item.entities.join(', ')}
                    </div>
                  )}

                  {/* Source IDs */}
                  {item.source_ids && item.source_ids.length > 0 && (
                    <div className="text-xs text-muted font-mono" style={{ marginTop: 2 }}>
                      refs: {item.source_ids.join(', ')}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Sources section */}
      {pool.sources && pool.sources.length > 0 && (
        <div className="run-detail-section">
          <div className="run-detail-section-header">
            <span className="run-detail-section-title">Sources</span>
            <span className="text-muted text-xs">{sourceCount} used</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {pool.sources.map((source, i) => (
              <div
                key={i}
                style={{
                  padding: '8px 12px',
                  background: 'var(--color-bg-secondary)',
                  border: '1px solid var(--color-border-subtle)',
                  borderRadius: 6,
                  fontSize: 12,
                  color: 'var(--color-text-secondary)',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                {typeof source === 'object'
                  ? Object.entries(source).map(([k, v]) => (
                      <span key={k} style={{ marginRight: 12 }}>
                        <span style={{ color: 'var(--color-text-muted)' }}>{k}:</span>{' '}
                        {String(v)}
                      </span>
                    ))
                  : String(source)}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Information Gaps section */}
      {pool.gaps && pool.gaps.length > 0 && (
        <div className="run-detail-section">
          <div className="run-detail-section-header">
            <span className="run-detail-section-title">Information Gaps</span>
            <span className="text-muted text-xs">{gapCount} identified</span>
          </div>
          <div className="evidence-gaps" style={{ marginTop: 0 }}>
            <ul className="evidence-gaps-list">
              {pool.gaps.map((gap, i) => (
                <li key={i}>{gap}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Empty state: no items */}
      {pool.items.length === 0 && pool.sources.length === 0 && pool.gaps.length === 0 && (
        <div className="run-detail-section">
          <span className="text-secondary text-sm">
            The evidence pool is empty — no items, sources, or gaps were recorded.
          </span>
        </div>
      )}
    </div>
  )
}

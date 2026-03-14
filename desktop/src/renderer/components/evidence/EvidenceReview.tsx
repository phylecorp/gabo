/**
 * @decision DEC-DESKTOP-EVIDENCE-REVIEW-001
 * @title EvidenceReview: interactive evidence curation with filter/toggle/submit
 * @status accepted
 * @rationale The curation UI lets users see all gathered evidence and selectively include
 *   or exclude items before analysis. Items are grouped by source type with visual badges
 *   for confidence, category, and verification status. Quick actions (Select All, Deselect
 *   All, High Confidence Only) enable efficient curation of large evidence pools.
 */
import type { EvidencePool } from '../../api/types'

interface Props {
  pool: EvidencePool
  selectedCount: number
  totalCount: number
  onToggleItem: (itemId: string) => void
  onSelectAll: () => void
  onDeselectAll: () => void
  onSelectByFilter: (filter: string) => void
  onSubmit: () => void
  onBack: () => void
  submitting: boolean
}

export default function EvidenceReview({
  pool,
  selectedCount,
  totalCount,
  onToggleItem,
  onSelectAll,
  onDeselectAll,
  onSelectByFilter,
  onSubmit,
  onBack,
  submitting,
}: Props) {
  const sourceCount = pool.sources?.length ?? 0
  const canSubmit = selectedCount > 0 && !submitting

  return (
    <div className="evidence-review">
      {/* Summary bar */}
      <div className="evidence-summary-bar">
        <span className="evidence-summary-count">
          <strong>{totalCount}</strong> items from{' '}
          <strong>{sourceCount}</strong> sources —{' '}
          <strong>{selectedCount}</strong> selected
        </span>
      </div>

      {/* Quick-action filter buttons */}
      <div className="evidence-actions">
        <button
          type="button"
          className="evidence-action-btn"
          onClick={onSelectAll}
          disabled={submitting}
        >
          Select All
        </button>
        <button
          type="button"
          className="evidence-action-btn"
          onClick={onDeselectAll}
          disabled={submitting}
        >
          Deselect All
        </button>
        <button
          type="button"
          className="evidence-action-btn"
          onClick={() => onSelectByFilter('high-confidence')}
          disabled={submitting}
        >
          High Confidence Only
        </button>
        <button
          type="button"
          className="evidence-action-btn"
          onClick={() => onSelectByFilter('research')}
          disabled={submitting}
        >
          Research Only
        </button>
        <button
          type="button"
          className="evidence-action-btn"
          onClick={() => onSelectByFilter('decomposition')}
          disabled={submitting}
        >
          Decomposition Only
        </button>
      </div>

      {/* Evidence item list */}
      <div className="evidence-items">
        {pool.items.map(item => (
          <div
            key={item.item_id}
            className={`evidence-item${item.selected ? '' : ' deselected'}`}
            onClick={() => !submitting && onToggleItem(item.item_id)}
            role="checkbox"
            aria-checked={item.selected}
            tabIndex={0}
            onKeyDown={e => {
              if ((e.key === ' ' || e.key === 'Enter') && !submitting) {
                onToggleItem(item.item_id)
              }
            }}
          >
            <input
              type="checkbox"
              className="evidence-item-checkbox"
              checked={item.selected}
              onChange={() => onToggleItem(item.item_id)}
              disabled={submitting}
              onClick={e => e.stopPropagation()}
              aria-label={`Toggle: ${item.claim}`}
            />
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
                  <span className="evidence-badge" style={{ background: 'rgba(152,152,176,0.1)', color: 'var(--color-text-secondary)' }}>
                    {item.category}
                  </span>
                )}

                {/* Verified checkmark */}
                {item.verified && (
                  <span className="evidence-badge evidence-badge-verified" title="Verified">
                    ✓ verified
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Information gaps */}
      {pool.gaps && pool.gaps.length > 0 && (
        <div className="evidence-gaps">
          <div className="evidence-gaps-title">Information Gaps</div>
          <ul className="evidence-gaps-list">
            {pool.gaps.map((gap, i) => (
              <li key={i}>{gap}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Footer */}
      <div className="evidence-footer">
        <button
          type="button"
          className={`btn-primary btn-lg${canSubmit ? '' : ' btn-disabled'}`}
          disabled={!canSubmit}
          onClick={onSubmit}
        >
          {submitting ? 'Starting analysis...' : `Run Analysis (${selectedCount} items)`}
        </button>
        <button
          type="button"
          className="evidence-action-btn"
          onClick={onBack}
          disabled={submitting}
        >
          Back
        </button>
      </div>
    </div>
  )
}

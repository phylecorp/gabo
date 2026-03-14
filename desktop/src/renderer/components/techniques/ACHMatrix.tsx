/**
 * @decision DEC-DESKTOP-ACH-MATRIX-001
 * @title ACHMatrix: interactive diagnosticity matrix with crosshair hover and inconsistency bars
 * @status accepted
 * @rationale ACH (Analysis of Competing Hypotheses) is the diagnostic flagship technique.
 *   The matrix layout — hypotheses as columns, evidence as rows — directly maps to the
 *   analytical logic: each cell represents whether a piece of evidence is consistent (C),
 *   inconsistent (I), or neutral (N) with a hypothesis. Inconsistency scores per
 *   hypothesis are the key output: lower scores indicate more likely hypotheses because
 *   fewer pieces of evidence contradict them. Crosshair hover helps analysts trace a
 *   single evidence row or hypothesis column across the full matrix without losing context.
 */
import { useState } from 'react'
import type { ACHResult, ACHRating } from '../../api/types'
import IntelCard from '../common/IntelCard'
import IntelBadge from '../common/IntelBadge'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

type HoverCell = { row: number; col: number } | null

function getRatingClass(rating: string): string {
  switch (rating) {
    case 'C':
      return 'ach-cell-c'
    case 'I':
      return 'ach-cell-i'
    case 'N':
    default:
      return 'ach-cell-n'
  }
}

function getRatingLabel(rating: string): string {
  switch (rating) {
    case 'C':
      return 'C'
    case 'I':
      return 'I'
    case 'N':
    default:
      return 'N'
  }
}

function InconsistencyBar({ score, max }: { score: number; max: number }) {
  const pct = max > 0 ? (score / max) * 100 : 0
  const colorClass =
    pct < 33 ? 'ach-bar-green' : pct < 66 ? 'ach-bar-amber' : 'ach-bar-red'

  return (
    <div className="ach-score-bar-wrapper">
      <div
        className={`ach-score-bar ${colorClass}`}
        style={{ width: `${pct}%` }}
      />
      <span className="ach-score-label">{score.toFixed(1)}</span>
    </div>
  )
}

function getCell(
  matrix: ACHRating[],
  evidenceId: string,
  hypothesisId: string
): ACHRating | undefined {
  return matrix.find(
    (r) => r.evidence_id === evidenceId && r.hypothesis_id === hypothesisId
  )
}

function CredibilityBadge({ level }: { level: string }) {
  const lvl = level?.toLowerCase() as 'high' | 'medium' | 'low'
  return <IntelBadge label={level || '?'} variant="confidence" level={lvl} />
}

export default function ACHMatrix({ data }: TechniqueRendererProps) {
  const result = data as ACHResult
  const [hovered, setHovered] = useState<HoverCell>(null)
  const [selectedCell, setSelectedCell] = useState<ACHRating | null>(null)

  if (!result?.hypotheses || !result?.evidence) {
    return (
      <IntelCard title="ACH Matrix" accent="green">
        <p className="text-secondary text-sm">No matrix data available.</p>
      </IntelCard>
    )
  }

  const { hypotheses, evidence, matrix, inconsistency_scores, most_likely, rejected } =
    result

  const maxScore = Math.max(...Object.values(inconsistency_scores || {}), 1)

  return (
    <div className="ach-container">
      {/* Summary */}
      <IntelCard accent="green" className="ach-summary-card">
        <p className="text-secondary" style={{ margin: 0 }}>{result.summary}</p>
      </IntelCard>

      {/* Matrix */}
      <IntelCard title="Diagnosticity Matrix" accent="green" className="ach-matrix-card">
        <div className="ach-matrix-scroll">
          <table className="ach-matrix">
            {/* Header: hypothesis columns */}
            <thead>
              <tr>
                <th className="ach-evidence-header">Evidence</th>
                {hypotheses.map((h, ci) => {
                  const isLikely = h.id === most_likely
                  const isRejected = rejected?.includes(h.id)
                  const isHovered = hovered?.col === ci
                  return (
                    <th
                      key={h.id}
                      className={`ach-hyp-header ${isHovered ? 'ach-crosshair-col' : ''}`}
                    >
                      <div className="ach-hyp-label">
                        <span className="ach-hyp-id">{h.id}</span>
                        {isLikely && (
                          <span className="ach-most-likely-badge">MOST LIKELY</span>
                        )}
                        {isRejected && (
                          <span className="ach-rejected-badge">REJECTED</span>
                        )}
                      </div>
                      <p
                        className={`ach-hyp-desc ${isRejected ? 'ach-rejected-text' : ''}`}
                        title={h.description}
                      >
                        {h.description.length > 60
                          ? h.description.slice(0, 60) + '…'
                          : h.description}
                      </p>
                    </th>
                  )
                })}
              </tr>
            </thead>

            <tbody>
              {/* Evidence rows */}
              {evidence.map((ev, ri) => {
                const isHoveredRow = hovered?.row === ri
                return (
                  <tr key={ev.id} className={isHoveredRow ? 'ach-crosshair-row' : ''}>
                    {/* Evidence cell */}
                    <td className="ach-evidence-cell">
                      <div className="ach-evidence-id">{ev.id}</div>
                      <p className="ach-evidence-desc" title={ev.description}>
                        {ev.description.length > 80
                          ? ev.description.slice(0, 80) + '…'
                          : ev.description}
                      </p>
                      <div className="ach-evidence-badges">
                        <CredibilityBadge level={ev.credibility} />
                      </div>
                    </td>

                    {/* Rating cells */}
                    {hypotheses.map((h, ci) => {
                      const cell = getCell(matrix, ev.id, h.id)
                      const rating = cell?.rating || 'N'
                      const isHoveredCol = hovered?.col === ci
                      const isSelected =
                        selectedCell?.evidence_id === ev.id &&
                        selectedCell?.hypothesis_id === h.id

                      return (
                        <td
                          key={h.id}
                          className={`ach-cell ${getRatingClass(rating)} ${
                            isHoveredRow || isHoveredCol ? 'ach-cell-highlight' : ''
                          } ${isSelected ? 'ach-cell-selected' : ''}`}
                          onMouseEnter={() => setHovered({ row: ri, col: ci })}
                          onMouseLeave={() => setHovered(null)}
                          onClick={() => setSelectedCell(cell || null)}
                          title={cell?.explanation || ''}
                        >
                          <span className="ach-cell-rating">
                            {getRatingLabel(rating)}
                          </span>
                        </td>
                      )
                    })}
                  </tr>
                )
              })}

              {/* Inconsistency scores row */}
              <tr className="ach-scores-row">
                <td className="ach-scores-label">Inconsistency Score</td>
                {hypotheses.map((h) => {
                  const score = inconsistency_scores?.[h.id] ?? 0
                  const isLikely = h.id === most_likely
                  return (
                    <td key={h.id} className={`ach-score-cell ${isLikely ? 'ach-score-cell-likely' : ''}`}>
                      <InconsistencyBar score={score} max={maxScore} />
                    </td>
                  )
                })}
              </tr>
            </tbody>
          </table>
        </div>

        {/* Selected cell explanation panel */}
        {selectedCell && (
          <div className="ach-explanation-panel">
            <div className="ach-explanation-header">
              <span className="ach-explanation-ids">
                {selectedCell.evidence_id} × {selectedCell.hypothesis_id}
              </span>
              <span className={`ach-cell-rating-label ${getRatingClass(selectedCell.rating)}`}>
                {selectedCell.rating === 'C'
                  ? 'Consistent'
                  : selectedCell.rating === 'I'
                  ? 'Inconsistent'
                  : 'Neutral'}
              </span>
              <button
                className="ach-explanation-close"
                onClick={() => setSelectedCell(null)}
              >
                ×
              </button>
            </div>
            <p className="ach-explanation-text">{selectedCell.explanation}</p>
          </div>
        )}
      </IntelCard>

      {/* Most likely + bottom line */}
      <div className="ach-conclusions">
        <IntelCard title="Most Likely Hypothesis" accent="cyan">
          <p className="text-secondary" style={{ margin: 0 }}>{most_likely}</p>
        </IntelCard>

        {rejected && rejected.length > 0 && (
          <IntelCard title="Rejected Hypotheses" accent="red">
            <ul className="ach-rejected-list">
              {rejected.map((r, i) => (
                <li key={i} className="ach-rejected-item">
                  {r}
                </li>
              ))}
            </ul>
          </IntelCard>
        )}
      </div>

      {/* Diagnosticity notes */}
      {result.diagnosticity_notes && (
        <CollapsibleSection title="Diagnosticity Notes" defaultOpen={false}>
          <p className="text-secondary text-sm">{result.diagnosticity_notes}</p>
        </CollapsibleSection>
      )}

      {/* Missing evidence */}
      {result.missing_evidence && result.missing_evidence.length > 0 && (
        <IntelCard title="Missing Evidence" accent="amber" className="ach-missing-card">
          <ul className="ach-missing-list">
            {result.missing_evidence.map((item, i) => (
              <li key={i} className="ach-missing-item">
                {item}
              </li>
            ))}
          </ul>
        </IntelCard>
      )}
    </div>
  )
}

registerRenderer('ach', ACHMatrix)

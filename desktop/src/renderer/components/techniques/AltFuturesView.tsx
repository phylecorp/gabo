/**
 * @decision DEC-DESKTOP-ALT-FUTURES-001
 * @title AltFuturesView: interactive 2x2 scenario matrix with axis objects and proper field mapping
 * @status accepted
 * @rationale Alternative Futures uses two orthogonal driving forces to generate four distinct
 *   future scenarios. The x_axis and y_axis fields are FuturesAxis objects with name/low_label/
 *   high_label — not plain strings. Scenarios use scenario_name (not name/title) and narrative
 *   (not description/summary). indicators is a list[str] — the old typeof check that filtered
 *   arrays is removed. focal_issue, key_uncertainties, and cross_cutting_indicators are new
 *   top-level fields. strategic_implications replaces the old implications field name.
 */
import { useState } from 'react'
import IntelCard from '../common/IntelCard'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

type QuadrantAccent = 'cyan' | 'green' | 'amber' | 'purple'

const QUADRANT_ACCENTS: QuadrantAccent[] = ['cyan', 'green', 'amber', 'purple']
const QUADRANT_LABELS = ['I', 'II', 'III', 'IV']

interface FuturesAxis {
  name?: string
  low_label?: string
  high_label?: string
}

interface ScenarioQuadrant {
  quadrant_label?: string
  scenario_name?: string
  narrative?: string
  indicators?: string[]
  policy_implications?: string
  [key: string]: any
}

export default function AltFuturesView({ data }: TechniqueRendererProps) {
  const [expandedQuadrant, setExpandedQuadrant] = useState<number | null>(null)

  const scenarios: ScenarioQuadrant[] = data?.scenarios || []
  const xAxis: FuturesAxis | null = data?.x_axis || null
  const yAxis: FuturesAxis | null = data?.y_axis || null
  const focalIssue: string = data?.focal_issue || ''
  const keyUncertainties: string[] = data?.key_uncertainties || []
  const crossCuttingIndicators: string[] = data?.cross_cutting_indicators || []
  const strategicImplications: string = data?.strategic_implications || ''

  if (scenarios.length === 0) {
    return (
      <IntelCard title="Alternative Futures" accent="purple">
        <p className="text-secondary text-sm">{data?.summary || 'No scenario data available.'}</p>
      </IntelCard>
    )
  }

  return (
    <div className="alt-futures-container">
      {/* Summary */}
      {data?.summary && (
        <IntelCard accent="purple" className="alt-futures-summary">
          <p className="text-secondary" style={{ margin: 0 }}>{data.summary}</p>
        </IntelCard>
      )}

      {/* Focal Issue */}
      {focalIssue && (
        <IntelCard title="Focal Issue" accent="purple">
          <p className="text-secondary" style={{ margin: 0 }}>{focalIssue}</p>
        </IntelCard>
      )}

      {/* Key Uncertainties */}
      {keyUncertainties.length > 0 && (
        <IntelCard title="Key Uncertainties" accent="purple">
          <ul className="technique-list">
            {keyUncertainties.map((u, i) => (
              <li key={i} className="technique-list-item text-secondary">{u}</li>
            ))}
          </ul>
        </IntelCard>
      )}

      {/* Axis labels */}
      {(xAxis || yAxis) && (
        <div className="alt-futures-axes">
          {xAxis && (
            <div className="alt-futures-axis-x">
              <span className="alt-futures-axis-label">{xAxis.name}</span>
              {xAxis.low_label && xAxis.high_label && (
                <span className="alt-futures-axis-range text-muted text-xs">
                  {xAxis.low_label} → {xAxis.high_label}
                </span>
              )}
              <span className="alt-futures-axis-arrow">→</span>
            </div>
          )}
          {yAxis && (
            <div className="alt-futures-axis-y">
              <span className="alt-futures-axis-arrow">↑</span>
              <span className="alt-futures-axis-label">{yAxis.name}</span>
              {yAxis.low_label && yAxis.high_label && (
                <span className="alt-futures-axis-range text-muted text-xs">
                  {yAxis.low_label} → {yAxis.high_label}
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* 2x2 grid */}
      <div className="alt-futures-grid">
        {scenarios.slice(0, 4).map((scenario, i) => {
          const accent = QUADRANT_ACCENTS[i % 4]
          const isExpanded = expandedQuadrant === i
          const title = scenario.scenario_name || `Scenario ${QUADRANT_LABELS[i]}`

          return (
            <div
              key={i}
              className={`alt-futures-quadrant alt-futures-quadrant-${accent} ${isExpanded ? 'alt-futures-quadrant-expanded' : ''}`}
              onClick={() => setExpandedQuadrant(isExpanded ? null : i)}
            >
              <div className="alt-futures-quadrant-header">
                <span className={`alt-futures-quadrant-id alt-futures-id-${accent}`}>
                  {QUADRANT_LABELS[i]}
                </span>
                <div style={{ flex: 1 }}>
                  <span className="alt-futures-quadrant-name">{title}</span>
                  {scenario.quadrant_label && (
                    <p className="text-muted text-xs" style={{ margin: 0 }}>{scenario.quadrant_label}</p>
                  )}
                </div>
                <span className="alt-futures-expand-hint">{isExpanded ? '▾' : '▸'}</span>
              </div>
              {isExpanded && (
                <div className="alt-futures-quadrant-body">
                  {scenario.narrative && (
                    <p className="text-secondary text-sm" style={{ marginBottom: 8 }}>{scenario.narrative}</p>
                  )}
                  {scenario.indicators && scenario.indicators.length > 0 && (
                    <div className="alt-futures-extra-field">
                      <span className="alt-futures-field-key">Indicators</span>
                      <ul className="technique-list">
                        {scenario.indicators.map((ind: string, j: number) => (
                          <li key={j} className="technique-list-item technique-list-item-warning text-secondary text-sm">{ind}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {scenario.policy_implications && (
                    <div className="alt-futures-extra-field">
                      <span className="alt-futures-field-key">Policy Implications</span>
                      <span className="text-secondary text-sm">{scenario.policy_implications}</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Cross-Cutting Indicators */}
      {crossCuttingIndicators.length > 0 && (
        <CollapsibleSection title="Cross-Cutting Indicators" defaultOpen={true}>
          <ul className="technique-list">
            {crossCuttingIndicators.map((ind, i) => (
              <li key={i} className="technique-list-item technique-list-item-warning text-secondary">{ind}</li>
            ))}
          </ul>
        </CollapsibleSection>
      )}

      {/* Strategic Implications */}
      {strategicImplications && (
        <CollapsibleSection title="Strategic Implications" defaultOpen={false}>
          <p className="text-secondary text-sm">{strategicImplications}</p>
        </CollapsibleSection>
      )}
    </div>
  )
}

registerRenderer('alt_futures', AltFuturesView)

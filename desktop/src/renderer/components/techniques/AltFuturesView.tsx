/**
 * @decision DEC-DESKTOP-ALT-FUTURES-001
 * @title AltFuturesView: interactive 2x2 scenario matrix with expandable quadrants
 * @status accepted
 * @rationale Alternative Futures uses two orthogonal driving forces to generate four
 *   distinct future scenarios. The 2x2 quadrant layout is the canonical format —
 *   it maps the analytical logic directly to spatial position. Each quadrant gets a
 *   distinct signal color for immediate differentiation. Click-to-expand reveals the
 *   full scenario description without cluttering the overview. The axis labels are
 *   derived from the driving forces extracted from the data.
 */
import { useState } from 'react'
import IntelCard from '../common/IntelCard'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

type QuadrantAccent = 'cyan' | 'green' | 'amber' | 'purple'

const QUADRANT_ACCENTS: QuadrantAccent[] = ['cyan', 'green', 'amber', 'purple']
const QUADRANT_LABELS = ['I', 'II', 'III', 'IV']

interface Scenario {
  name?: string
  title?: string
  description?: string
  summary?: string
  [key: string]: any
}

function extractScenarios(data: any): Scenario[] {
  // API may return scenarios under various keys
  if (Array.isArray(data.scenarios)) return data.scenarios
  if (Array.isArray(data.quadrants)) return data.quadrants
  if (Array.isArray(data.futures)) return data.futures
  // Fallback: look for any array of objects with name/title/description
  for (const key of Object.keys(data)) {
    const val = data[key]
    if (Array.isArray(val) && val.length >= 2 && val[0]?.name) return val
  }
  return []
}

function extractDrivingForces(data: any): { x: string; y: string } {
  return {
    x: data.driving_force_x || data.x_axis || data.force_x || 'Driving Force X',
    y: data.driving_force_y || data.y_axis || data.force_y || 'Driving Force Y',
  }
}

export default function AltFuturesView({ data }: TechniqueRendererProps) {
  const [expandedQuadrant, setExpandedQuadrant] = useState<number | null>(null)
  const scenarios = extractScenarios(data)
  const forces = extractDrivingForces(data)

  if (scenarios.length === 0) {
    // Generic fallback
    return (
      <IntelCard title="Alternative Futures" accent="purple">
        <p className="text-secondary text-sm">{data?.summary || 'No scenario data available.'}</p>
        <pre className="ach-json-fallback">{JSON.stringify(data, null, 2)}</pre>
      </IntelCard>
    )
  }

  return (
    <div className="alt-futures-container">
      {/* Summary */}
      {data.summary && (
        <IntelCard accent="purple" className="alt-futures-summary">
          <p className="text-secondary" style={{ margin: 0 }}>{data.summary}</p>
        </IntelCard>
      )}

      {/* Axis labels */}
      <div className="alt-futures-axes">
        <div className="alt-futures-axis-x">
          <span className="alt-futures-axis-label">{forces.x}</span>
          <span className="alt-futures-axis-arrow">→</span>
        </div>
        <div className="alt-futures-axis-y">
          <span className="alt-futures-axis-arrow">↑</span>
          <span className="alt-futures-axis-label">{forces.y}</span>
        </div>
      </div>

      {/* 2x2 grid */}
      <div className="alt-futures-grid">
        {scenarios.slice(0, 4).map((scenario, i) => {
          const accent = QUADRANT_ACCENTS[i % 4]
          const isExpanded = expandedQuadrant === i
          const title = scenario.name || scenario.title || `Scenario ${QUADRANT_LABELS[i]}`
          const desc = scenario.description || scenario.summary || ''

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
                <span className="alt-futures-quadrant-name">{title}</span>
                <span className="alt-futures-expand-hint">{isExpanded ? '▾' : '▸'}</span>
              </div>
              {isExpanded && (
                <div className="alt-futures-quadrant-body">
                  <p className="text-secondary text-sm">{desc}</p>
                  {/* Render any additional scenario fields */}
                  {Object.entries(scenario)
                    .filter(([k]) => !['name', 'title', 'description', 'summary'].includes(k))
                    .map(([k, v]) => (
                      typeof v === 'string' ? (
                        <div key={k} className="alt-futures-extra-field">
                          <span className="alt-futures-field-key">{k.replace(/_/g, ' ')}</span>
                          <span className="text-secondary text-sm">{v}</span>
                        </div>
                      ) : null
                    ))}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Implications */}
      {data.implications && (
        <CollapsibleSection title="Strategic Implications" defaultOpen={false}>
          {Array.isArray(data.implications)
            ? (
              <ul className="technique-list">
                {data.implications.map((imp: string, i: number) => (
                  <li key={i} className="technique-list-item text-secondary">{imp}</li>
                ))}
              </ul>
            )
            : <p className="text-secondary text-sm">{data.implications}</p>
          }
        </CollapsibleSection>
      )}

      {/* Planning considerations */}
      {data.planning_considerations && (
        <CollapsibleSection title="Planning Considerations" defaultOpen={false}>
          {Array.isArray(data.planning_considerations)
            ? (
              <ul className="technique-list">
                {data.planning_considerations.map((item: string, i: number) => (
                  <li key={i} className="technique-list-item text-secondary">{item}</li>
                ))}
              </ul>
            )
            : <p className="text-secondary text-sm">{data.planning_considerations}</p>
          }
        </CollapsibleSection>
      )}
    </div>
  )
}

registerRenderer('alt_futures', AltFuturesView)

/**
 * @decision DEC-DESKTOP-INDICATORS-001
 * @title IndicatorsView: indicator table aligned to Indicator model fields
 * @status accepted
 * @rationale Fixed field name mismatches that caused 8-13% display rate. The model
 *   uses topic (not hypothesis/related_hypothesis), current_status (not tracking_status/status),
 *   notes (not significance), and has no timeframe field. Added trend display
 *   (Worsening/Stable/Improving), hypothesis_or_scenario at the top, trigger_mechanisms
 *   and overall_trajectory which were in the model but never rendered.
 */
import IntelCard from '../common/IntelCard'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

interface Indicator {
  topic?: string
  indicator?: string
  current_status?: string
  trend?: string
  notes?: string
  [key: string]: any
}

function StatusBadge({ status }: { status?: string }) {
  if (!status) return null
  const s = status.toLowerCase()
  const cls =
    s.includes('serious') ? 'badge-red'
      : s.includes('substantial') ? 'badge-amber'
      : s.includes('moderate') ? 'badge-amber'
      : s.includes('low') ? 'badge-green'
      : 'badge-default'
  return <span className={`intel-badge ${cls}`}>{status}</span>
}

function TrendBadge({ trend }: { trend?: string }) {
  if (!trend) return null
  const t = trend.toLowerCase()
  const cls =
    t === 'worsening' ? 'badge-red'
      : t === 'improving' ? 'badge-green'
      : 'badge-default'
  return <span className={`intel-badge ${cls}`}>{trend}</span>
}

export default function IndicatorsView({ data }: TechniqueRendererProps) {
  const indicators: Indicator[] = data?.indicators || []
  const triggerMechanisms: string[] = data?.trigger_mechanisms || []

  return (
    <div className="technique-container">
      {data?.hypothesis_or_scenario && (
        <IntelCard title="Hypothesis / Scenario" accent="cyan">
          <p className="text-secondary" style={{ margin: 0 }}>{data.hypothesis_or_scenario}</p>
        </IntelCard>
      )}

      {data?.summary && !data?.hypothesis_or_scenario && (
        <IntelCard accent="cyan">
          <p className="text-secondary" style={{ margin: 0 }}>{data.summary}</p>
        </IntelCard>
      )}

      {indicators.length > 0 && (
        <IntelCard title="Indicators & Signposts" accent="cyan">
          <div className="intel-table-wrapper">
            <table className="intel-table">
              <thead>
                <tr>
                  <th>Topic</th>
                  <th>Indicator / Observable</th>
                  <th>Status</th>
                  <th>Trend</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {indicators.map((ind, i) => (
                  <tr key={i}>
                    <td className="text-secondary text-sm">{ind.topic || '—'}</td>
                    <td>{ind.indicator || '—'}</td>
                    <td>
                      <StatusBadge status={ind.current_status} />
                    </td>
                    <td>
                      <TrendBadge trend={ind.trend} />
                    </td>
                    <td className="text-secondary text-sm">{ind.notes || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </IntelCard>
      )}

      {data?.overall_trajectory && (
        <IntelCard title="Overall Trajectory" accent="green">
          <p className="text-secondary" style={{ margin: 0 }}>{data.overall_trajectory}</p>
        </IntelCard>
      )}

      {triggerMechanisms.length > 0 && (
        <IntelCard title="Trigger Mechanisms" accent="amber">
          <ul className="technique-list">
            {triggerMechanisms.map((t, i) => (
              <li key={i} className="technique-list-item technique-list-item-warning">{t}</li>
            ))}
          </ul>
        </IntelCard>
      )}
    </div>
  )
}

registerRenderer('indicators', IndicatorsView)

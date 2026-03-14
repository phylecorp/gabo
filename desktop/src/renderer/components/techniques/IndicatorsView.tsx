import IntelCard from '../common/IntelCard'
import IntelBadge from '../common/IntelBadge'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

interface Indicator {
  indicator?: string
  event?: string
  description?: string
  observable?: string
  hypothesis?: string
  related_hypothesis?: string
  tracking_status?: string
  status?: string
  significance?: string
  timeframe?: string
  [key: string]: any
}

function StatusBadge({ status }: { status?: string }) {
  if (!status) return null
  const s = status.toLowerCase()
  const variant =
    s === 'observed' || s === 'confirmed' ? 'badge-green'
      : s === 'pending' || s === 'watching' ? 'badge-amber'
      : s === 'not observed' || s === 'absent' ? 'badge-red'
      : 'badge-default'
  return <span className={`intel-badge ${variant}`}>{status}</span>
}

export default function IndicatorsView({ data }: TechniqueRendererProps) {
  const indicators: Indicator[] =
    data?.indicators || data?.signposts || data?.key_indicators || []

  return (
    <div className="technique-container">
      {data?.summary && (
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
                  <th>Indicator / Observable Event</th>
                  <th>Related Hypothesis</th>
                  <th>Status</th>
                  <th>Significance</th>
                  <th>Timeframe</th>
                </tr>
              </thead>
              <tbody>
                {indicators.map((ind, i) => (
                  <tr key={i}>
                    <td>{ind.indicator || ind.event || ind.description || ind.observable || '—'}</td>
                    <td className="text-secondary text-sm">
                      {ind.hypothesis || ind.related_hypothesis || '—'}
                    </td>
                    <td>
                      <StatusBadge status={ind.tracking_status || ind.status} />
                    </td>
                    <td className="text-secondary text-sm">
                      {ind.significance || '—'}
                    </td>
                    <td className="text-secondary text-sm">
                      {ind.timeframe || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </IntelCard>
      )}

      {data?.collection_priorities && (
        <CollapsibleSection title="Collection Priorities" defaultOpen={false}>
          {Array.isArray(data.collection_priorities)
            ? (
              <ul className="technique-list">
                {data.collection_priorities.map((item: string, i: number) => (
                  <li key={i} className="technique-list-item text-secondary">{item}</li>
                ))}
              </ul>
            )
            : <p className="text-secondary text-sm">{data.collection_priorities}</p>
          }
        </CollapsibleSection>
      )}

      {data?.warning_thresholds && (
        <IntelCard title="Warning Thresholds" accent="amber">
          {Array.isArray(data.warning_thresholds)
            ? (
              <ul className="technique-list">
                {data.warning_thresholds.map((item: string, i: number) => (
                  <li key={i} className="technique-list-item technique-list-item-warning">{item}</li>
                ))}
              </ul>
            )
            : <p className="text-secondary text-sm">{data.warning_thresholds}</p>
          }
        </IntelCard>
      )}
    </div>
  )
}

registerRenderer('indicators', IndicatorsView)

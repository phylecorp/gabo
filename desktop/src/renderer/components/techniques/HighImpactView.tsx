import IntelCard from '../common/IntelCard'
import IntelBadge from '../common/IntelBadge'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

interface HighImpactEvent {
  event?: string
  scenario?: string
  description?: string
  probability?: string
  likelihood?: string
  impact?: string
  impact_level?: string
  pathways?: string[]
  indicators?: string[]
  [key: string]: any
}

function ProbabilityBadge({ level }: { level?: string }) {
  if (!level) return null
  const s = level.toLowerCase()
  const cls = s === 'high' ? 'badge-amber'
    : s === 'medium' ? 'badge-cyan'
    : 'badge-green'
  return <span className={`intel-badge ${cls}`}>P: {level}</span>
}

function ImpactBadge({ level }: { level?: string }) {
  if (!level) return null
  const s = level.toLowerCase()
  const cls = s === 'catastrophic' || s === 'critical' || s === 'high' ? 'badge-red'
    : s === 'major' || s === 'medium' ? 'badge-amber'
    : 'badge-default'
  return <span className={`intel-badge ${cls}`}>Impact: {level}</span>
}

export default function HighImpactView({ data }: TechniqueRendererProps) {
  const events: HighImpactEvent[] =
    data?.high_impact_scenarios || data?.scenarios || data?.events || data?.low_probability_events || []

  return (
    <div className="technique-container">
      {data?.summary && (
        <IntelCard accent="red">
          <p className="text-secondary" style={{ margin: 0 }}>{data.summary}</p>
        </IntelCard>
      )}

      {events.length > 0 && events.map((evt, i) => (
        <IntelCard
          key={i}
          title={evt.event || evt.scenario || evt.description || `Scenario ${i + 1}`}
          accent="red"
        >
          <div className="highimpact-badges" style={{ marginBottom: 8 }}>
            <ProbabilityBadge level={evt.probability || evt.likelihood} />
            <ImpactBadge level={evt.impact || evt.impact_level} />
          </div>

          {evt.description && evt.event && (
            <p className="text-secondary text-sm">{evt.description}</p>
          )}

          {evt.pathways && evt.pathways.length > 0 && (
            <div className="highimpact-pathways">
              <p className="highimpact-section-label">Plausible Pathways</p>
              <ul className="technique-list">
                {evt.pathways.map((p: string, j: number) => (
                  <li key={j} className="technique-list-item text-secondary">{p}</li>
                ))}
              </ul>
            </div>
          )}

          {evt.indicators && evt.indicators.length > 0 && (
            <div className="highimpact-indicators">
              <p className="highimpact-section-label">Watch Indicators</p>
              <ul className="technique-list">
                {evt.indicators.map((ind: string, j: number) => (
                  <li key={j} className="technique-list-item technique-list-item-warning">{ind}</li>
                ))}
              </ul>
            </div>
          )}
        </IntelCard>
      ))}

      {data?.mitigation_strategies && (
        <CollapsibleSection title="Mitigation Strategies" defaultOpen={false}>
          {Array.isArray(data.mitigation_strategies)
            ? (
              <ul className="technique-list">
                {data.mitigation_strategies.map((s: string, i: number) => (
                  <li key={i} className="technique-list-item text-secondary">{s}</li>
                ))}
              </ul>
            )
            : <p className="text-secondary text-sm">{data.mitigation_strategies}</p>
          }
        </CollapsibleSection>
      )}

      {data?.monitoring_priorities && (
        <CollapsibleSection title="Monitoring Priorities" defaultOpen={false}>
          {Array.isArray(data.monitoring_priorities)
            ? (
              <ul className="technique-list">
                {data.monitoring_priorities.map((s: string, i: number) => (
                  <li key={i} className="technique-list-item technique-list-item-warning">{s}</li>
                ))}
              </ul>
            )
            : <p className="text-secondary text-sm">{data.monitoring_priorities}</p>
          }
        </CollapsibleSection>
      )}
    </div>
  )
}

registerRenderer('high_impact', HighImpactView)

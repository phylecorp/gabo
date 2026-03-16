/**
 * @decision DEC-DESKTOP-HIGHIMPACT-001
 * @title HighImpactView: pathway-based display of unlikely-but-consequential events
 * @status accepted
 * @rationale The High-Impact/Low-Probability method uses a structured sequence: define the
 *   event, explain why it's currently unlikely, assess the impact, then develop plausible
 *   pathways. Each pathway is a full object with triggers and indicators — not a flat list.
 *   Plausibility badges on each pathway use the Pathway.plausibility literal values
 *   (Possible/Plausible/Remote). Deflection factors and policy implications cap the analysis.
 */
import IntelCard from '../common/IntelCard'
import IntelBadge from '../common/IntelBadge'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

interface Pathway {
  name?: string
  description?: string
  triggers?: string[]
  indicators?: string[]
  plausibility?: string
  [key: string]: any
}

function PlausibilityBadge({ level }: { level?: string }) {
  if (!level) return null
  const s = level.toLowerCase()
  const variant = s === 'plausible' ? 'amber' : s === 'possible' ? 'cyan' : 'green'
  return <span className={`intel-badge badge-${variant}`}>{level}</span>
}

export default function HighImpactView({ data }: TechniqueRendererProps) {
  const eventDefinition: string = data?.event_definition || ''
  const whyConsidered: string = data?.why_considered_unlikely || ''
  const impactAssessment: string = data?.impact_assessment || ''
  const pathways: Pathway[] = data?.pathways || []
  const deflectionFactors: string[] = data?.deflection_factors || []
  const policyImplications: string = data?.policy_implications || ''

  return (
    <div className="technique-container">
      {data?.summary && (
        <IntelCard accent="red">
          <p className="text-secondary" style={{ margin: 0 }}>{data.summary}</p>
        </IntelCard>
      )}

      {/* Event Definition */}
      {eventDefinition && (
        <IntelCard title="Event Definition" accent="red">
          <p className="text-secondary" style={{ margin: 0 }}>{eventDefinition}</p>
        </IntelCard>
      )}

      {/* Why Considered Unlikely + Impact Assessment — side by side */}
      {(whyConsidered || impactAssessment) && (
        <div className="technique-two-col">
          {whyConsidered && (
            <IntelCard title="Why Considered Unlikely" accent="green">
              <p className="text-secondary" style={{ margin: 0 }}>{whyConsidered}</p>
            </IntelCard>
          )}
          {impactAssessment && (
            <IntelCard title="Impact Assessment" accent="amber">
              <p className="text-secondary" style={{ margin: 0 }}>{impactAssessment}</p>
            </IntelCard>
          )}
        </div>
      )}

      {/* Pathways */}
      {pathways.length > 0 && (
        <div>
          <h4 className="technique-section-heading">Plausible Pathways</h4>
          {pathways.map((pathway, i) => (
            <IntelCard
              key={i}
              title={pathway.name || `Pathway ${i + 1}`}
              accent="red"
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <PlausibilityBadge level={pathway.plausibility} />
              </div>

              {pathway.description && (
                <p className="text-secondary text-sm" style={{ marginBottom: 8 }}>{pathway.description}</p>
              )}

              {pathway.triggers && pathway.triggers.length > 0 && (
                <div className="highimpact-pathways">
                  <p className="highimpact-section-label">Triggers</p>
                  <ul className="technique-list">
                    {pathway.triggers.map((t: string, j: number) => (
                      <li key={j} className="technique-list-item text-secondary">{t}</li>
                    ))}
                  </ul>
                </div>
              )}

              {pathway.indicators && pathway.indicators.length > 0 && (
                <div className="highimpact-indicators">
                  <p className="highimpact-section-label">Watch Indicators</p>
                  <ul className="technique-list">
                    {pathway.indicators.map((ind: string, j: number) => (
                      <li key={j} className="technique-list-item technique-list-item-warning">{ind}</li>
                    ))}
                  </ul>
                </div>
              )}
            </IntelCard>
          ))}
        </div>
      )}

      {/* Deflection Factors */}
      {deflectionFactors.length > 0 && (
        <IntelCard title="Deflection Factors" accent="green">
          <ul className="technique-list">
            {deflectionFactors.map((f, i) => (
              <li key={i} className="technique-list-item text-secondary">{f}</li>
            ))}
          </ul>
        </IntelCard>
      )}

      {/* Policy Implications */}
      {policyImplications && (
        <CollapsibleSection title="Policy Implications" defaultOpen={false}>
          <p className="text-secondary text-sm">{policyImplications}</p>
        </CollapsibleSection>
      )}
    </div>
  )
}

registerRenderer('high_impact', HighImpactView)

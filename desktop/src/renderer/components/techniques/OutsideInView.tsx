import IntelCard from '../common/IntelCard'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

type SteepCategory = 'social' | 'technological' | 'economic' | 'environmental' | 'political'

interface SteepFactor {
  factor?: string
  description?: string
  impact?: string
  significance?: string
  trend?: string
  [key: string]: any
}

const STEEP_CONFIG: Record<SteepCategory, { label: string; accent: 'cyan' | 'green' | 'amber' | 'purple' | 'red' }> = {
  social: { label: 'Social', accent: 'cyan' },
  technological: { label: 'Technological', accent: 'purple' },
  economic: { label: 'Economic', accent: 'green' },
  environmental: { label: 'Environmental', accent: 'green' },
  political: { label: 'Political', accent: 'amber' },
}

function SteepPanel({ category, factors }: { category: SteepCategory; factors: SteepFactor[] }) {
  const { label, accent } = STEEP_CONFIG[category]
  if (!factors || factors.length === 0) return null

  return (
    <IntelCard title={label} accent={accent}>
      <ul className="technique-list">
        {factors.map((f, i) => (
          <li key={i} className="outside-in-factor">
            <p className="outside-in-factor-text">
              {f.factor || f.description || (typeof f === 'string' ? f : '—')}
            </p>
            {f.impact && (
              <p className="outside-in-factor-impact text-secondary text-sm">
                Impact: {f.impact}
              </p>
            )}
            {f.trend && (
              <p className="outside-in-factor-trend text-muted text-xs">
                Trend: {f.trend}
              </p>
            )}
          </li>
        ))}
      </ul>
    </IntelCard>
  )
}

export default function OutsideInView({ data }: TechniqueRendererProps) {
  const steep = data?.steep_factors || data?.steep || {}

  const socialFactors: SteepFactor[] =
    steep.social || data?.social_factors || []
  const techFactors: SteepFactor[] =
    steep.technological || steep.technology || data?.technological_factors || data?.technology_factors || []
  const econFactors: SteepFactor[] =
    steep.economic || data?.economic_factors || []
  const envFactors: SteepFactor[] =
    steep.environmental || data?.environmental_factors || []
  const polFactors: SteepFactor[] =
    steep.political || data?.political_factors || []

  const externalFactors: SteepFactor[] =
    data?.external_factors || data?.outside_factors || []

  return (
    <div className="technique-container">
      {data?.summary && (
        <IntelCard accent="cyan">
          <p className="text-secondary" style={{ margin: 0 }}>{data.summary}</p>
        </IntelCard>
      )}

      {/* STEEP grid */}
      <div className="outside-in-steep-grid">
        <SteepPanel category="social" factors={socialFactors} />
        <SteepPanel category="technological" factors={techFactors} />
        <SteepPanel category="economic" factors={econFactors} />
        <SteepPanel category="environmental" factors={envFactors} />
        <SteepPanel category="political" factors={polFactors} />
      </div>

      {/* Fallback: flat external factors if no STEEP structure */}
      {externalFactors.length > 0 &&
        !socialFactors.length && !techFactors.length && !econFactors.length && (
        <IntelCard title="External Factors" accent="cyan">
          <ul className="technique-list">
            {externalFactors.map((f, i) => (
              <li key={i} className="outside-in-factor">
                <p className="outside-in-factor-text">
                  {f.factor || f.description || (typeof f === 'string' ? f : '—')}
                </p>
                {f.impact && (
                  <p className="outside-in-factor-impact text-secondary text-sm">
                    Impact: {f.impact}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </IntelCard>
      )}

      {data?.key_insights && (
        <CollapsibleSection title="Key Insights" defaultOpen={true}>
          {Array.isArray(data.key_insights)
            ? (
              <ul className="technique-list">
                {data.key_insights.map((s: string, i: number) => (
                  <li key={i} className="technique-list-item text-secondary">{s}</li>
                ))}
              </ul>
            )
            : <p className="text-secondary text-sm">{data.key_insights}</p>
          }
        </CollapsibleSection>
      )}

      {data?.strategic_implications && (
        <CollapsibleSection title="Strategic Implications" defaultOpen={false}>
          {Array.isArray(data.strategic_implications)
            ? (
              <ul className="technique-list">
                {data.strategic_implications.map((s: string, i: number) => (
                  <li key={i} className="technique-list-item text-secondary">{s}</li>
                ))}
              </ul>
            )
            : <p className="text-secondary text-sm">{data.strategic_implications}</p>
          }
        </CollapsibleSection>
      )}
    </div>
  )
}

registerRenderer('outside_in', OutsideInView)

import IntelCard from '../common/IntelCard'
import IntelBadge from '../common/IntelBadge'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

interface Assumption {
  assumption?: string
  statement?: string
  description?: string
  confidence?: string
  confidence_level?: string
  what_would_undermine?: string
  undermined_by?: string
  impact_if_wrong?: string
  vulnerability?: string
  vulnerable?: boolean
  [key: string]: any
}

function ConfidenceBadge({ level }: { level?: string }) {
  if (!level) return null
  const lvl = level.toLowerCase()
  const badgeLevel = lvl === 'high' ? 'high' : lvl === 'medium' ? 'medium' : 'low'
  return <IntelBadge label={level} variant="confidence" level={badgeLevel} />
}

function isVulnerable(a: Assumption): boolean {
  if (a.vulnerable === true) return true
  const conf = (a.confidence || a.confidence_level || '').toLowerCase()
  return conf === 'low'
}

export default function AssumptionsView({ data }: TechniqueRendererProps) {
  const assumptions: Assumption[] = data?.assumptions || data?.key_assumptions || []
  const vulnerable = assumptions.filter(isVulnerable)

  if (assumptions.length === 0) {
    return (
      <IntelCard title="Key Assumptions" accent="green">
        <p className="text-secondary text-sm">{data?.summary || 'No assumptions data.'}</p>
      </IntelCard>
    )
  }

  return (
    <div className="technique-container">
      {data?.summary && (
        <IntelCard accent="green">
          <p className="text-secondary" style={{ margin: 0 }}>{data.summary}</p>
        </IntelCard>
      )}

      {vulnerable.length > 0 && (
        <IntelCard title="Most Vulnerable Assumptions" accent="red">
          <ul className="technique-list">
            {vulnerable.map((a, i) => (
              <li key={i} className="assumption-item assumption-item-vulnerable">
                <p className="assumption-statement">
                  {a.assumption || a.statement || a.description}
                </p>
                {(a.what_would_undermine || a.undermined_by) && (
                  <p className="assumption-undermine text-sm">
                    <span className="assumption-field-label">Undermined by: </span>
                    {a.what_would_undermine || a.undermined_by}
                  </p>
                )}
                {(a.impact_if_wrong || a.vulnerability) && (
                  <p className="assumption-impact text-sm">
                    <span className="assumption-field-label">Impact if wrong: </span>
                    {a.impact_if_wrong || a.vulnerability}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </IntelCard>
      )}

      <IntelCard title="All Assumptions" accent="green">
        <div className="assumptions-table-wrapper">
          <table className="intel-table">
            <thead>
              <tr>
                <th>Assumption</th>
                <th>Confidence</th>
                <th>What Would Undermine</th>
                <th>Impact If Wrong</th>
              </tr>
            </thead>
            <tbody>
              {assumptions.map((a, i) => (
                <tr key={i} className={isVulnerable(a) ? 'assumption-row-vulnerable' : ''}>
                  <td className="assumption-td-main">
                    {a.assumption || a.statement || a.description || '—'}
                  </td>
                  <td>
                    <ConfidenceBadge
                      level={a.confidence || a.confidence_level}
                    />
                  </td>
                  <td className="text-secondary text-sm">
                    {a.what_would_undermine || a.undermined_by || '—'}
                  </td>
                  <td className="text-secondary text-sm">
                    {a.impact_if_wrong || a.vulnerability || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </IntelCard>

      {data?.critical_assumptions && (
        <CollapsibleSection title="Critical Assumptions" defaultOpen={true}>
          {Array.isArray(data.critical_assumptions)
            ? (
              <ul className="technique-list">
                {data.critical_assumptions.map((item: string, i: number) => (
                  <li key={i} className="technique-list-item text-secondary">{item}</li>
                ))}
              </ul>
            )
            : <p className="text-secondary text-sm">{data.critical_assumptions}</p>
          }
        </CollapsibleSection>
      )}
    </div>
  )
}

registerRenderer('assumptions', AssumptionsView)

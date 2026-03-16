/**
 * @decision DEC-DESKTOP-ASSUMPTIONS-001
 * @title AssumptionsView: renders KeyAssumptionsResult with correct field names and full metadata
 * @status accepted
 * @rationale The model field is `what_undermines` (not `what_would_undermine`). The renderer
 *   now accesses this correctly. analytic_line provides context for the entire analysis.
 *   basis_for_confidence explains why each assumption is believed. most_vulnerable is the
 *   LLM's explicit vulnerability ranking shown directly (not recomputed from confidence levels).
 *   recommended_monitoring surfaces actionable tracking items. The table displays all 5
 *   per-assumption fields.
 */
import IntelCard from '../common/IntelCard'
import IntelBadge from '../common/IntelBadge'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

interface Assumption {
  assumption?: string
  confidence?: string
  basis_for_confidence?: string
  what_undermines?: string
  impact_if_wrong?: string
  [key: string]: any
}

function ConfidenceBadge({ level }: { level?: string }) {
  if (!level) return null
  const lvl = level.toLowerCase()
  const badgeLevel = lvl === 'high' ? 'high' : lvl === 'medium' ? 'medium' : 'low'
  return <IntelBadge label={level} variant="confidence" level={badgeLevel} />
}

export default function AssumptionsView({ data }: TechniqueRendererProps) {
  const analyticLine: string = data?.analytic_line || ''
  const assumptions: Assumption[] = data?.assumptions || []
  const mostVulnerable: string[] = data?.most_vulnerable || []
  const recommendedMonitoring: string[] = data?.recommended_monitoring || []

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

      {/* The analytic judgment being examined */}
      {analyticLine && (
        <IntelCard title="Analytic Line" accent="amber">
          <p className="text-secondary" style={{ margin: 0, fontStyle: 'italic' }}>{analyticLine}</p>
        </IntelCard>
      )}

      {/* LLM's explicit vulnerability ranking */}
      {mostVulnerable.length > 0 && (
        <IntelCard title="Most Vulnerable Assumptions" accent="red">
          <ul className="technique-list">
            {mostVulnerable.map((vuln, i) => (
              <li key={i} className="assumption-item assumption-item-vulnerable">
                <p className="assumption-statement" style={{ margin: 0 }}>{vuln}</p>
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
                <th>Basis for Confidence</th>
                <th>What Undermines</th>
                <th>Impact If Wrong</th>
              </tr>
            </thead>
            <tbody>
              {assumptions.map((a, i) => (
                <tr key={i}>
                  <td className="assumption-td-main">
                    {a.assumption || '—'}
                  </td>
                  <td>
                    <ConfidenceBadge level={a.confidence} />
                  </td>
                  <td className="text-secondary text-sm">
                    {a.basis_for_confidence || '—'}
                  </td>
                  <td className="text-secondary text-sm">
                    {a.what_undermines || '—'}
                  </td>
                  <td className="text-secondary text-sm">
                    {a.impact_if_wrong || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </IntelCard>

      {/* Actionable monitoring items */}
      {recommendedMonitoring.length > 0 && (
        <IntelCard title="Recommended Monitoring" accent="cyan">
          <ul className="technique-list">
            {recommendedMonitoring.map((item, i) => (
              <li key={i} className="technique-list-item text-secondary">{item}</li>
            ))}
          </ul>
        </IntelCard>
      )}
    </div>
  )
}

registerRenderer('assumptions', AssumptionsView)

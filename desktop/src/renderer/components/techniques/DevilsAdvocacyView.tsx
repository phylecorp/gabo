import IntelCard from '../common/IntelCard'
import IntelBadge from '../common/IntelBadge'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

interface CounterChallenge {
  point?: string
  argument?: string
  challenge?: string
  evidence?: string
  severity?: string
  [key: string]: any
}

function SeverityBadge({ severity }: { severity?: string }) {
  if (!severity) return null
  const s = severity.toLowerCase()
  const cls = s === 'high' || s === 'critical' ? 'badge-red'
    : s === 'medium' ? 'badge-amber'
    : 'badge-green'
  return <span className={`intel-badge ${cls}`}>{severity}</span>
}

export default function DevilsAdvocacyView({ data }: TechniqueRendererProps) {
  const dominantView: string =
    data?.dominant_view || data?.original_position || data?.consensus_view || ''
  const counterCase: string =
    data?.devils_advocate_case || data?.counter_argument || data?.alternative_case || ''
  const challenges: CounterChallenge[] =
    data?.key_challenges || data?.challenges || data?.counter_points || []
  const conclusion: string =
    data?.conclusion || data?.revised_assessment || ''

  return (
    <div className="technique-container">
      {data?.summary && (
        <IntelCard accent="amber">
          <p className="text-secondary" style={{ margin: 0 }}>{data.summary}</p>
        </IntelCard>
      )}

      {/* Two-column: dominant view vs devil's advocate */}
      <div className="technique-two-col">
        {dominantView && (
          <IntelCard title="Dominant View" accent="cyan">
            <p className="text-secondary" style={{ margin: 0 }}>{dominantView}</p>
          </IntelCard>
        )}
        {counterCase && (
          <IntelCard title="Devil's Advocate Case" accent="amber">
            <p className="text-secondary" style={{ margin: 0 }}>{counterCase}</p>
          </IntelCard>
        )}
      </div>

      {/* Key challenges */}
      {challenges.length > 0 && (
        <IntelCard title="Key Challenges" accent="red">
          <ul className="technique-list">
            {challenges.map((c, i) => (
              <li key={i} className="challenge-item">
                <div className="challenge-header">
                  <span className="challenge-text">
                    {c.point || c.argument || c.challenge}
                  </span>
                  <SeverityBadge severity={c.severity} />
                </div>
                {c.evidence && (
                  <p className="challenge-evidence text-secondary text-sm">
                    {c.evidence}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </IntelCard>
      )}

      {/* Conclusion */}
      {conclusion && (
        <IntelCard title="Conclusion / Revised Assessment" accent="green">
          <p className="text-secondary" style={{ margin: 0 }}>{conclusion}</p>
        </IntelCard>
      )}

      {/* Vulnerabilities */}
      {data?.vulnerabilities && (
        <CollapsibleSection title="Vulnerabilities Identified" defaultOpen={false}>
          {Array.isArray(data.vulnerabilities)
            ? (
              <ul className="technique-list">
                {data.vulnerabilities.map((v: string, i: number) => (
                  <li key={i} className="technique-list-item text-secondary">{v}</li>
                ))}
              </ul>
            )
            : <p className="text-secondary text-sm">{data.vulnerabilities}</p>
          }
        </CollapsibleSection>
      )}
    </div>
  )
}

registerRenderer('devils_advocacy', DevilsAdvocacyView)

import IntelCard from '../common/IntelCard'
import IntelBadge from '../common/IntelBadge'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

interface LikelyAction {
  action?: string
  description?: string
  capability?: string
  rationale?: string
  confidence?: string
  [key: string]: any
}

function ConfidenceBadge({ level }: { level?: string }) {
  if (!level) return null
  const lvl = level.toLowerCase() as 'high' | 'medium' | 'low'
  return <IntelBadge label={level} variant="confidence" level={lvl} />
}

export default function RedTeamView({ data }: TechniqueRendererProps) {
  const adversaryPerspective: string =
    data?.adversary_perspective || data?.adversary_view || data?.perspective || ''
  const likelyActions: LikelyAction[] =
    data?.likely_actions || data?.actions || data?.adversary_actions || []
  const capabilities: string[] =
    data?.capabilities || data?.adversary_capabilities || []
  const intentions: string[] =
    data?.intentions || data?.adversary_intentions || []
  const vulnerabilities: string[] =
    data?.identified_vulnerabilities || data?.our_vulnerabilities || data?.exploitable_gaps || []
  const blindspots: string[] =
    data?.analytical_blindspots || data?.our_blindspots || []

  return (
    <div className="technique-container">
      {data?.summary && (
        <IntelCard accent="red">
          <p className="text-secondary" style={{ margin: 0 }}>{data.summary}</p>
        </IntelCard>
      )}

      {/* Adversary perspective overview */}
      {adversaryPerspective && (
        <IntelCard title="Adversary Perspective" accent="red">
          <p className="text-secondary" style={{ margin: 0 }}>{adversaryPerspective}</p>
        </IntelCard>
      )}

      {/* Likely actions */}
      {likelyActions.length > 0 && (
        <IntelCard title="Likely Actions" accent="red">
          <ul className="technique-list">
            {likelyActions.map((action, i) => (
              <li key={i} className="redteam-action-item">
                <div className="redteam-action-header">
                  <span className="redteam-action-text">
                    {action.action || action.description}
                  </span>
                  <ConfidenceBadge level={action.confidence} />
                </div>
                {action.rationale && (
                  <p className="redteam-action-rationale text-secondary text-sm">
                    {action.rationale}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </IntelCard>
      )}

      <div className="technique-two-col">
        {/* Capabilities */}
        {capabilities.length > 0 && (
          <IntelCard title="Adversary Capabilities" accent="amber">
            <ul className="technique-list">
              {capabilities.map((cap, i) => (
                <li key={i} className="technique-list-item text-secondary">{cap}</li>
              ))}
            </ul>
          </IntelCard>
        )}

        {/* Intentions */}
        {intentions.length > 0 && (
          <IntelCard title="Adversary Intentions" accent="purple">
            <ul className="technique-list">
              {intentions.map((intent, i) => (
                <li key={i} className="technique-list-item text-secondary">{intent}</li>
              ))}
            </ul>
          </IntelCard>
        )}
      </div>

      {/* Our vulnerabilities */}
      {vulnerabilities.length > 0 && (
        <IntelCard title="Identified Vulnerabilities" accent="red">
          <ul className="technique-list">
            {vulnerabilities.map((v, i) => (
              <li key={i} className="technique-list-item technique-list-item-gap">{v}</li>
            ))}
          </ul>
        </IntelCard>
      )}

      {/* Analytical blind spots */}
      {blindspots.length > 0 && (
        <CollapsibleSection title="Analytical Blind Spots" defaultOpen={false}>
          <ul className="technique-list">
            {blindspots.map((b, i) => (
              <li key={i} className="technique-list-item technique-list-item-warning">{b}</li>
            ))}
          </ul>
        </CollapsibleSection>
      )}

      {data?.recommended_countermeasures && (
        <CollapsibleSection title="Recommended Countermeasures" defaultOpen={false}>
          {Array.isArray(data.recommended_countermeasures)
            ? (
              <ul className="technique-list">
                {data.recommended_countermeasures.map((c: string, i: number) => (
                  <li key={i} className="technique-list-item text-secondary">{c}</li>
                ))}
              </ul>
            )
            : <p className="text-secondary text-sm">{data.recommended_countermeasures}</p>
          }
        </CollapsibleSection>
      )}
    </div>
  )
}

registerRenderer('red_team', RedTeamView)

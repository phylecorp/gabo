/**
 * @decision DEC-DESKTOP-REDTEAM-001
 * @title RedTeamView: adversary role-play display with first-person memo as core artifact
 * @status accepted
 * @rationale The first_person_memo is the primary artifact of Red Team analysis — it represents
 *   authentic perspective-taking by embodying the adversary's voice. It deserves prominent
 *   blockquote treatment to distinguish it from analytical text. Supporting fields (identity,
 *   context, perceptions, motivations, constraints, predicted actions) build the analytical
 *   scaffolding around the memo.
 */
import IntelCard from '../common/IntelCard'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

export default function RedTeamView({ data }: TechniqueRendererProps) {
  const adversaryIdentity: string = data?.adversary_identity || ''
  const adversaryContext: string = data?.adversary_context || ''
  const perceptionOfThreats: string = data?.perception_of_threats || ''
  const perceptionOfOpportunities: string = data?.perception_of_opportunities || ''
  const firstPersonMemo: string = data?.first_person_memo || ''
  const predictedActions: string[] = data?.predicted_actions || []
  const keyMotivations: string[] = data?.key_motivations || []
  const constraintsOnAdversary: string[] = data?.constraints_on_adversary || []

  return (
    <div className="technique-container">
      {data?.summary && (
        <IntelCard accent="red">
          <p className="text-secondary" style={{ margin: 0 }}>{data.summary}</p>
        </IntelCard>
      )}

      {/* Adversary Identity */}
      {adversaryIdentity && (
        <IntelCard title="Adversary Identity" accent="red">
          <p className="text-secondary" style={{ margin: 0 }}>{adversaryIdentity}</p>
        </IntelCard>
      )}

      {/* Adversary Context */}
      {adversaryContext && (
        <IntelCard title="Adversary Context" accent="red">
          <p className="text-secondary" style={{ margin: 0 }}>{adversaryContext}</p>
        </IntelCard>
      )}

      {/* Perceptions — side by side when both present */}
      {(perceptionOfThreats || perceptionOfOpportunities) && (
        <div className="technique-two-col">
          {perceptionOfThreats && (
            <IntelCard title="Perception of Threats" accent="amber">
              <p className="text-secondary" style={{ margin: 0 }}>{perceptionOfThreats}</p>
            </IntelCard>
          )}
          {perceptionOfOpportunities && (
            <IntelCard title="Perception of Opportunities" accent="green">
              <p className="text-secondary" style={{ margin: 0 }}>{perceptionOfOpportunities}</p>
            </IntelCard>
          )}
        </div>
      )}

      {/* First-Person Memo — THE core artifact, prominent blockquote */}
      {firstPersonMemo && (
        <IntelCard title="First-Person Memo" accent="red">
          <blockquote className="redteam-memo-blockquote">
            {firstPersonMemo}
          </blockquote>
        </IntelCard>
      )}

      {/* Predicted Actions */}
      {predictedActions.length > 0 && (
        <IntelCard title="Predicted Actions" accent="red">
          <ul className="technique-list">
            {predictedActions.map((action, i) => (
              <li key={i} className="technique-list-item text-secondary">{action}</li>
            ))}
          </ul>
        </IntelCard>
      )}

      {/* Key Motivations + Constraints — side by side */}
      {(keyMotivations.length > 0 || constraintsOnAdversary.length > 0) && (
        <div className="technique-two-col">
          {keyMotivations.length > 0 && (
            <IntelCard title="Key Motivations" accent="purple">
              <ul className="technique-list">
                {keyMotivations.map((m, i) => (
                  <li key={i} className="technique-list-item text-secondary">{m}</li>
                ))}
              </ul>
            </IntelCard>
          )}
          {constraintsOnAdversary.length > 0 && (
            <IntelCard title="Constraints on Adversary" accent="amber">
              <ul className="technique-list">
                {constraintsOnAdversary.map((c, i) => (
                  <li key={i} className="technique-list-item text-secondary">{c}</li>
                ))}
              </ul>
            </IntelCard>
          )}
        </div>
      )}
    </div>
  )
}

registerRenderer('red_team', RedTeamView)

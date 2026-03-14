/**
 * @decision DEC-DESKTOP-ADVERSARIAL-EXCHANGE-001
 * @title AdversarialExchange: critique/rebuttal timeline visualization
 * @status accepted
 * @rationale Adversarial analysis has a structured exchange pattern: a critique
 *   identifies challenges at varying severity, then a rebuttal accepts or rejects
 *   each. Displaying them as a timeline with a vertical connector reinforces the
 *   temporal/logical flow. Severity badges use confidence color semantics (high
 *   severity = red, moderate = amber, low = green) which are the most intuitive
 *   signal mapping.
 */
import type { CritiqueResult, RebuttalResult } from '../../api/types'
import IntelBadge from '../common/IntelBadge'
import CollapsibleSection from '../common/CollapsibleSection'

interface AdversarialExchangeProps {
  critique: CritiqueResult
  rebuttal?: RebuttalResult
}

function severityLevel(s: string): 'high' | 'medium' | 'low' {
  const lower = s.toLowerCase()
  if (lower === 'high' || lower === 'critical' || lower === 'severe') return 'high'
  if (lower === 'low' || lower === 'minor') return 'low'
  return 'medium'
}

export default function AdversarialExchange({ critique, rebuttal }: AdversarialExchangeProps) {
  return (
    <div className="adversarial-exchange">
      {/* Critique side */}
      <div className="adversarial-block adversarial-critique">
        <div className="adversarial-block-header">
          <span className="adversarial-block-label">Critique</span>
          <IntelBadge
            label={`${critique.severity} severity`}
            variant="severity"
            level={severityLevel(critique.severity)}
          />
        </div>
        <p className="adversarial-block-summary">{critique.overall_assessment}</p>

        {critique.challenges.length > 0 && (
          <div className="adversarial-challenges">
            <div className="adversarial-sub-label">Challenges</div>
            {critique.challenges.map((c, i) => (
              <div key={i} className="adversarial-challenge">
                <IntelBadge
                  label={c.severity}
                  variant="severity"
                  level={severityLevel(c.severity)}
                />
                <span className="adversarial-challenge-point">{c.point}</span>
                {c.evidence && (
                  <span className="adversarial-challenge-evidence text-muted">{c.evidence}</span>
                )}
              </div>
            ))}
          </div>
        )}

        {critique.alternative_interpretations.length > 0 && (
          <CollapsibleSection title="Alternative Interpretations" count={critique.alternative_interpretations.length} defaultOpen={false}>
            <ul className="adversarial-list">
              {critique.alternative_interpretations.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          </CollapsibleSection>
        )}
      </div>

      {/* Timeline connector */}
      {rebuttal && (
        <div className="adversarial-connector">
          <div className="adversarial-connector-line" />
          <span className="adversarial-connector-label">REBUTTAL</span>
          <div className="adversarial-connector-line" />
        </div>
      )}

      {/* Rebuttal side */}
      {rebuttal && (
        <div className="adversarial-block adversarial-rebuttal">
          <div className="adversarial-block-header">
            <span className="adversarial-block-label">Rebuttal</span>
          </div>
          <p className="adversarial-block-summary">{rebuttal.revised_conclusions}</p>

          {rebuttal.accepted_challenges.length > 0 && (
            <div className="adversarial-accepted">
              <div className="adversarial-sub-label adversarial-sub-label-amber">
                Accepted Challenges ({rebuttal.accepted_challenges.length})
              </div>
              <ul className="adversarial-list">
                {rebuttal.accepted_challenges.map((a, i) => (
                  <li key={i} className="adversarial-accepted-item">{a}</li>
                ))}
              </ul>
            </div>
          )}

          {rebuttal.rejected_challenges.length > 0 && (
            <CollapsibleSection title="Rejected Challenges" count={rebuttal.rejected_challenges.length} defaultOpen={false}>
              {rebuttal.rejected_challenges.map((r, i) => (
                <div key={i} className="adversarial-rejected-item">
                  <span className="adversarial-challenge-point">{r.challenge}</span>
                  <span className="adversarial-rebuttal-text text-muted">{r.rebuttal}</span>
                </div>
              ))}
            </CollapsibleSection>
          )}
        </div>
      )}
    </div>
  )
}

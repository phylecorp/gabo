/**
 * @decision DEC-DESKTOP-DA-001
 * @title DevilsAdvocacyView: aligned to DevilsAdvocacyResult model fields
 * @status accepted
 * @rationale Fixed field name mismatches that caused 8-13% display rate. The model
 *   uses mainline_judgment (not dominant_view/original_position/consensus_view),
 *   challenged_assumptions as structured ChallengedAssumption objects (not key_challenges
 *   array of strings), alternative_hypothesis (not devils_advocate_case/counter_argument).
 *   Added mainline_evidence, supporting_evidence_for_alternative, quality_of_evidence_concerns,
 *   and recommended_actions which were in the model but never rendered. ChallengedAssumption
 *   cards now show assumption, challenge, evidence_against, and vulnerability badge.
 */
import IntelCard from '../common/IntelCard'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

interface ChallengedAssumption {
  assumption?: string
  challenge?: string
  evidence_against?: string
  vulnerability?: string
  [key: string]: any
}

function VulnerabilityBadge({ level }: { level?: string }) {
  if (!level) return null
  const l = level.toLowerCase()
  const cls = l === 'high' ? 'badge-red' : l === 'medium' ? 'badge-amber' : 'badge-green'
  return <span className={`intel-badge ${cls}`}>{level} Vulnerability</span>
}

function ConclusionBadge({ conclusion }: { conclusion?: string }) {
  if (!conclusion) return null
  const c = conclusion.toLowerCase()
  const cls = c.includes('overturned') ? 'badge-red'
    : c.includes('weakened') ? 'badge-amber'
    : 'badge-green'
  return <span className={`intel-badge ${cls}`} style={{ fontSize: '0.875rem', padding: '4px 10px' }}>{conclusion}</span>
}

export default function DevilsAdvocacyView({ data }: TechniqueRendererProps) {
  const challengedAssumptions: ChallengedAssumption[] = data?.challenged_assumptions || []
  const mainlineEvidence: string[] = data?.mainline_evidence || []
  const supportingEvidence: string[] = data?.supporting_evidence_for_alternative || []
  const evidenceConcerns: string[] = data?.quality_of_evidence_concerns || []
  const recommendedActions: string[] = data?.recommended_actions || []

  return (
    <div className="technique-container">
      {data?.summary && (
        <IntelCard accent="amber">
          <p className="text-secondary" style={{ margin: 0 }}>{data.summary}</p>
        </IntelCard>
      )}

      {/* Two-column: mainline vs alternative */}
      <div className="technique-two-col">
        {data?.mainline_judgment && (
          <IntelCard title="Mainline Judgment" accent="cyan">
            <p className="text-secondary" style={{ margin: 0 }}>{data.mainline_judgment}</p>
            {mainlineEvidence.length > 0 && (
              <ul className="technique-list" style={{ marginTop: 12 }}>
                {mainlineEvidence.map((e, i) => (
                  <li key={i} className="technique-list-item technique-list-item-positive text-sm">{e}</li>
                ))}
              </ul>
            )}
          </IntelCard>
        )}

        {data?.alternative_hypothesis && (
          <IntelCard title="Alternative Hypothesis" accent="amber">
            <p className="text-secondary" style={{ margin: 0 }}>{data.alternative_hypothesis}</p>
            {supportingEvidence.length > 0 && (
              <ul className="technique-list" style={{ marginTop: 12 }}>
                {supportingEvidence.map((e, i) => (
                  <li key={i} className="technique-list-item technique-list-item-positive text-sm">{e}</li>
                ))}
              </ul>
            )}
          </IntelCard>
        )}
      </div>

      {/* Challenged assumptions as cards */}
      {challengedAssumptions.length > 0 && (
        <IntelCard title="Challenged Assumptions" accent="red">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {challengedAssumptions.map((ca, i) => (
              <div key={i} className="intel-card intel-card-default" style={{ padding: '12px 16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                  <span style={{ fontWeight: 600, fontSize: '0.875rem' }}>{ca.assumption || '—'}</span>
                  <VulnerabilityBadge level={ca.vulnerability} />
                </div>
                {ca.challenge && (
                  <p className="text-secondary text-sm" style={{ margin: '4px 0' }}>
                    <strong>Challenge:</strong> {ca.challenge}
                  </p>
                )}
                {ca.evidence_against && (
                  <p className="text-secondary text-sm" style={{ margin: '4px 0' }}>
                    <strong>Evidence against:</strong> {ca.evidence_against}
                  </p>
                )}
              </div>
            ))}
          </div>
        </IntelCard>
      )}

      {/* Conclusion */}
      {data?.conclusion && (
        <IntelCard title="Conclusion" accent="green">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <ConclusionBadge conclusion={data.conclusion} />
          </div>
        </IntelCard>
      )}

      {/* Evidence concerns */}
      {evidenceConcerns.length > 0 && (
        <IntelCard title="Evidence Quality Concerns" accent="amber">
          <ul className="technique-list">
            {evidenceConcerns.map((c, i) => (
              <li key={i} className="technique-list-item technique-list-item-warning">{c}</li>
            ))}
          </ul>
        </IntelCard>
      )}

      {/* Recommended actions */}
      {recommendedActions.length > 0 && (
        <CollapsibleSection title="Recommended Actions" defaultOpen={false}>
          <ul className="technique-list">
            {recommendedActions.map((r, i) => (
              <li key={i} className="technique-list-item text-secondary">{r}</li>
            ))}
          </ul>
        </CollapsibleSection>
      )}
    </div>
  )
}

registerRenderer('devils_advocacy', DevilsAdvocacyView)

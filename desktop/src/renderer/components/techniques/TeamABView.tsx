/**
 * @decision DEC-DESKTOP-TEAMAB-001
 * @title TeamABView: aligned to TeamABResult and TeamPosition model fields
 * @status accepted
 * @rationale Fixed field name mismatches that caused 8-13% display rate. The model
 *   uses team.team (not team.name for display label), team.argument (not team.position),
 *   jury_assessment (not synthesis), and has stronger_case and recommended_research
 *   fields that were never rendered. Each TeamPosition also has hypothesis, key_assumptions,
 *   key_evidence, and acknowledged_weaknesses which were not displayed. Added a
 *   debate_points table showing topic, team A/B positions, and resolution.
 */
import IntelCard from '../common/IntelCard'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

interface TeamPosition {
  team?: string
  hypothesis?: string
  key_assumptions?: string[]
  key_evidence?: string[]
  argument?: string
  acknowledged_weaknesses?: string[]
  [key: string]: any
}

interface DebatePoint {
  topic?: string
  team_a_position?: string
  team_b_position?: string
  resolution?: string
  [key: string]: any
}

function StrongerCaseBadge({ side }: { side?: string }) {
  if (!side) return null
  if (side === 'Indeterminate') return <span className="intel-badge badge-default">Indeterminate</span>
  const cls = side === 'A' ? 'badge-green' : 'badge-amber'
  return <span className={`intel-badge ${cls}`}>Team {side} Stronger</span>
}

function TeamCard({
  position,
  accent,
}: {
  position: TeamPosition | null | undefined
  accent: 'cyan' | 'amber'
}) {
  if (!position) return null
  const teamLabel = position.team ? `Team ${position.team}` : 'Team'
  const assumptions: string[] = position.key_assumptions || []
  const evidence: string[] = position.key_evidence || []
  const weaknesses: string[] = position.acknowledged_weaknesses || []

  return (
    <IntelCard title={teamLabel} accent={accent}>
      {position.hypothesis && (
        <div style={{ marginBottom: 10 }}>
          <p className="text-sm" style={{ fontWeight: 600, marginBottom: 4 }}>Hypothesis</p>
          <p className="text-secondary text-sm" style={{ margin: 0 }}>{position.hypothesis}</p>
        </div>
      )}

      {assumptions.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <p className="text-sm" style={{ fontWeight: 600, marginBottom: 4 }}>Key Assumptions</p>
          <ul className="technique-list">
            {assumptions.map((a, i) => (
              <li key={i} className="technique-list-item text-secondary text-sm">{a}</li>
            ))}
          </ul>
        </div>
      )}

      {evidence.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <p className="text-sm" style={{ fontWeight: 600, marginBottom: 4 }}>Key Evidence</p>
          <ul className="technique-list">
            {evidence.map((e, i) => (
              <li key={i} className="technique-list-item technique-list-item-positive text-sm">{e}</li>
            ))}
          </ul>
        </div>
      )}

      {position.argument && (
        <div style={{ marginBottom: 10 }}>
          <p className="text-sm" style={{ fontWeight: 600, marginBottom: 4 }}>Argument</p>
          <p className="text-secondary text-sm" style={{ margin: 0 }}>{position.argument}</p>
        </div>
      )}

      {weaknesses.length > 0 && (
        <div>
          <p className="text-sm" style={{ fontWeight: 600, marginBottom: 4 }}>Acknowledged Weaknesses</p>
          <ul className="technique-list">
            {weaknesses.map((w, i) => (
              <li key={i} className="technique-list-item technique-list-item-warning text-sm">{w}</li>
            ))}
          </ul>
        </div>
      )}
    </IntelCard>
  )
}

export default function TeamABView({ data }: TechniqueRendererProps) {
  const debatePoints: DebatePoint[] = data?.debate_points || []
  const areasOfAgreement: string[] = data?.areas_of_agreement || []
  const recommendedResearch: string[] = data?.recommended_research || []

  return (
    <div className="technique-container">
      {data?.summary && (
        <IntelCard accent="purple">
          <p className="text-secondary" style={{ margin: 0 }}>{data.summary}</p>
        </IntelCard>
      )}

      {/* Two-column team comparison */}
      <div className="technique-two-col">
        <TeamCard position={data?.team_a} accent="cyan" />
        <TeamCard position={data?.team_b} accent="amber" />
      </div>

      {/* Debate points table */}
      {debatePoints.length > 0 && (
        <IntelCard title="Debate Points" accent="purple">
          <div className="intel-table-wrapper">
            <table className="intel-table">
              <thead>
                <tr>
                  <th>Topic</th>
                  <th>Team A Position</th>
                  <th>Team B Position</th>
                  <th>Resolution</th>
                </tr>
              </thead>
              <tbody>
                {debatePoints.map((dp, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 600 }}>{dp.topic || '—'}</td>
                    <td className="text-secondary text-sm">{dp.team_a_position || '—'}</td>
                    <td className="text-secondary text-sm">{dp.team_b_position || '—'}</td>
                    <td className="text-secondary text-sm">{dp.resolution || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </IntelCard>
      )}

      {/* Jury assessment */}
      {data?.jury_assessment && (
        <IntelCard title="Jury Assessment" accent="green">
          <div style={{ marginBottom: data?.stronger_case ? 10 : 0 }}>
            <p className="text-secondary" style={{ margin: 0 }}>{data.jury_assessment}</p>
          </div>
          {data?.stronger_case && (
            <div style={{ marginTop: 8 }}>
              <StrongerCaseBadge side={data.stronger_case} />
            </div>
          )}
        </IntelCard>
      )}

      {/* Areas of agreement */}
      {areasOfAgreement.length > 0 && (
        <CollapsibleSection title="Areas of Agreement" defaultOpen={false}>
          <ul className="technique-list">
            {areasOfAgreement.map((item, i) => (
              <li key={i} className="technique-list-item technique-list-item-positive">{item}</li>
            ))}
          </ul>
        </CollapsibleSection>
      )}

      {/* Recommended research */}
      {recommendedResearch.length > 0 && (
        <CollapsibleSection title="Recommended Research" defaultOpen={false}>
          <ul className="technique-list">
            {recommendedResearch.map((r, i) => (
              <li key={i} className="technique-list-item text-secondary">{r}</li>
            ))}
          </ul>
        </CollapsibleSection>
      )}
    </div>
  )
}

registerRenderer('team_ab', TeamABView)

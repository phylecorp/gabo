import IntelCard from '../common/IntelCard'
import IntelBadge from '../common/IntelBadge'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

interface TeamArgument {
  point?: string
  argument?: string
  claim?: string
  evidence?: string
  strength?: string
  [key: string]: any
}

function StrengthBadge({ strength }: { strength?: string }) {
  if (!strength) return null
  const s = strength.toLowerCase()
  const cls = s === 'strong' || s === 'high' ? 'badge-green'
    : s === 'moderate' || s === 'medium' ? 'badge-amber'
    : 'badge-red'
  return <span className={`intel-badge ${cls}`}>{strength}</span>
}

export default function TeamABView({ data }: TechniqueRendererProps) {
  const teamAArgs: TeamArgument[] =
    data?.team_a_arguments || data?.team_a?.arguments || data?.team_a?.points || []
  const teamBArgs: TeamArgument[] =
    data?.team_b_arguments || data?.team_b?.arguments || data?.team_b?.points || []

  const teamAName: string =
    data?.team_a_name || data?.team_a?.name || 'Team A'
  const teamBName: string =
    data?.team_b_name || data?.team_b?.name || 'Team B'

  const teamAPosition: string =
    data?.team_a_position || data?.team_a?.position || ''
  const teamBPosition: string =
    data?.team_b_position || data?.team_b?.position || ''

  const teamAStrength: string =
    data?.team_a_strength || data?.team_a?.overall_strength || ''
  const teamBStrength: string =
    data?.team_b_strength || data?.team_b?.overall_strength || ''

  return (
    <div className="technique-container">
      {data?.summary && (
        <IntelCard accent="purple">
          <p className="text-secondary" style={{ margin: 0 }}>{data.summary}</p>
        </IntelCard>
      )}

      {/* Two-column team comparison */}
      <div className="technique-two-col">
        {/* Team A */}
        <IntelCard
          title={teamAName}
          subtitle={teamAStrength ? `Strength: ${teamAStrength}` : undefined}
          accent="cyan"
        >
          {teamAPosition && (
            <p className="team-position text-secondary">{teamAPosition}</p>
          )}
          {teamAStrength && (
            <div style={{ marginBottom: 8 }}>
              <StrengthBadge strength={teamAStrength} />
            </div>
          )}
          {teamAArgs.length > 0 && (
            <ul className="technique-list">
              {teamAArgs.map((arg, i) => (
                <li key={i} className="team-arg-item">
                  <p className="team-arg-text">
                    {arg.point || arg.argument || arg.claim}
                  </p>
                  {arg.evidence && (
                    <p className="team-arg-evidence text-secondary text-sm">
                      {arg.evidence}
                    </p>
                  )}
                  {arg.strength && (
                    <StrengthBadge strength={arg.strength} />
                  )}
                </li>
              ))}
            </ul>
          )}
        </IntelCard>

        {/* Team B */}
        <IntelCard
          title={teamBName}
          subtitle={teamBStrength ? `Strength: ${teamBStrength}` : undefined}
          accent="amber"
        >
          {teamBPosition && (
            <p className="team-position text-secondary">{teamBPosition}</p>
          )}
          {teamBStrength && (
            <div style={{ marginBottom: 8 }}>
              <StrengthBadge strength={teamBStrength} />
            </div>
          )}
          {teamBArgs.length > 0 && (
            <ul className="technique-list">
              {teamBArgs.map((arg, i) => (
                <li key={i} className="team-arg-item">
                  <p className="team-arg-text">
                    {arg.point || arg.argument || arg.claim}
                  </p>
                  {arg.evidence && (
                    <p className="team-arg-evidence text-secondary text-sm">
                      {arg.evidence}
                    </p>
                  )}
                  {arg.strength && (
                    <StrengthBadge strength={arg.strength} />
                  )}
                </li>
              ))}
            </ul>
          )}
        </IntelCard>
      </div>

      {/* Synthesis / adjudication */}
      {data?.synthesis && (
        <IntelCard title="Synthesis" accent="green">
          <p className="text-secondary" style={{ margin: 0 }}>{data.synthesis}</p>
        </IntelCard>
      )}

      {data?.areas_of_agreement && (
        <CollapsibleSection title="Areas of Agreement" defaultOpen={false}>
          {Array.isArray(data.areas_of_agreement)
            ? (
              <ul className="technique-list">
                {data.areas_of_agreement.map((item: string, i: number) => (
                  <li key={i} className="technique-list-item technique-list-item-positive">{item}</li>
                ))}
              </ul>
            )
            : <p className="text-secondary text-sm">{data.areas_of_agreement}</p>
          }
        </CollapsibleSection>
      )}
    </div>
  )
}

registerRenderer('team_ab', TeamABView)

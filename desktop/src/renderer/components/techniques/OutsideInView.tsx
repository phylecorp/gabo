/**
 * @decision DEC-DESKTOP-OUTSIDEIN-001
 * @title OutsideInView: STEEP forces grouping from flat forces[] array by category field
 * @status accepted
 * @rationale The OutsideInResult model uses a flat forces[] list where each STEEPForce has
 *   a `category` field (Social/Technological/Economic/Environmental/Political). The renderer
 *   must group these at render time into STEEP buckets — not expect a pre-grouped dict.
 *   Each force also uses `force` (name), `impact_on_issue`, `controllability`, and `evidence`
 *   fields — not the old `factor`, `impact`, `trend` field names. The model field is
 *   `implications`, not `strategic_implications`.
 */
import IntelCard from '../common/IntelCard'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

type SteepCategory = 'Social' | 'Technological' | 'Economic' | 'Environmental' | 'Political'

interface STEEPForce {
  category?: SteepCategory
  force?: string
  description?: string
  impact_on_issue?: string
  controllability?: string
  evidence?: string
  [key: string]: any
}

const STEEP_CONFIG: Record<SteepCategory, { label: string; accent: 'cyan' | 'green' | 'amber' | 'purple' | 'red' }> = {
  Social: { label: 'Social', accent: 'cyan' },
  Technological: { label: 'Technological', accent: 'purple' },
  Economic: { label: 'Economic', accent: 'green' },
  Environmental: { label: 'Environmental', accent: 'green' },
  Political: { label: 'Political', accent: 'amber' },
}

function ControllabilityBadge({ level }: { level?: string }) {
  if (!level) return null
  const s = level.toLowerCase()
  const cls = s === 'controllable' ? 'badge-green'
    : s === 'partially controllable' ? 'badge-amber'
    : 'badge-red'
  return <span className={`intel-badge ${cls}`}>{level}</span>
}

function SteepPanel({ category, forces }: { category: SteepCategory; forces: STEEPForce[] }) {
  const { label, accent } = STEEP_CONFIG[category]
  if (!forces || forces.length === 0) return null

  return (
    <IntelCard title={label} accent={accent}>
      <ul className="technique-list">
        {forces.map((f, i) => (
          <li key={i} className="outside-in-factor">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <p className="outside-in-factor-text" style={{ margin: 0, fontWeight: 500 }}>
                {f.force || f.description || '—'}
              </p>
              <ControllabilityBadge level={f.controllability} />
            </div>
            {f.description && f.force && (
              <p className="text-secondary text-sm" style={{ marginBottom: 4 }}>{f.description}</p>
            )}
            {f.impact_on_issue && (
              <p className="outside-in-factor-impact text-secondary text-sm">
                Impact: {f.impact_on_issue}
              </p>
            )}
            {f.evidence && (
              <p className="outside-in-factor-trend text-muted text-xs">
                Evidence: {f.evidence}
              </p>
            )}
          </li>
        ))}
      </ul>
    </IntelCard>
  )
}

export default function OutsideInView({ data }: TechniqueRendererProps) {
  // Group flat forces[] by category at render time
  const allForces: STEEPForce[] = data?.forces || []
  const grouped: Record<SteepCategory, STEEPForce[]> = {
    Social: [],
    Technological: [],
    Economic: [],
    Environmental: [],
    Political: [],
  }
  for (const force of allForces) {
    if (force.category && grouped[force.category]) {
      grouped[force.category].push(force)
    }
  }

  const keyExternalDrivers: string[] = data?.key_external_drivers || []
  const overlookedFactors: string[] = data?.overlooked_factors || []
  const implications: string = data?.implications || ''

  return (
    <div className="technique-container">
      {data?.summary && (
        <IntelCard accent="cyan">
          <p className="text-secondary" style={{ margin: 0 }}>{data.summary}</p>
        </IntelCard>
      )}

      {/* Issue Description */}
      {data?.issue_description && (
        <IntelCard title="Issue Under Analysis" accent="cyan">
          <p className="text-secondary" style={{ margin: 0 }}>{data.issue_description}</p>
        </IntelCard>
      )}

      {/* STEEP grid */}
      <div className="outside-in-steep-grid">
        <SteepPanel category="Social" forces={grouped.Social} />
        <SteepPanel category="Technological" forces={grouped.Technological} />
        <SteepPanel category="Economic" forces={grouped.Economic} />
        <SteepPanel category="Environmental" forces={grouped.Environmental} />
        <SteepPanel category="Political" forces={grouped.Political} />
      </div>

      {/* Key External Drivers */}
      {keyExternalDrivers.length > 0 && (
        <IntelCard title="Key External Drivers" accent="cyan">
          <ul className="technique-list">
            {keyExternalDrivers.map((d, i) => (
              <li key={i} className="technique-list-item text-secondary">{d}</li>
            ))}
          </ul>
        </IntelCard>
      )}

      {/* Overlooked Factors */}
      {overlookedFactors.length > 0 && (
        <CollapsibleSection title="Overlooked Factors" defaultOpen={true}>
          <ul className="technique-list">
            {overlookedFactors.map((f, i) => (
              <li key={i} className="technique-list-item technique-list-item-warning">{f}</li>
            ))}
          </ul>
        </CollapsibleSection>
      )}

      {/* Implications */}
      {implications && (
        <CollapsibleSection title="Strategic Implications" defaultOpen={false}>
          <p className="text-secondary text-sm">{implications}</p>
        </CollapsibleSection>
      )}
    </div>
  )
}

registerRenderer('outside_in', OutsideInView)

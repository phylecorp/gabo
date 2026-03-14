/**
 * @decision DEC-DESKTOP-FINDINGS-GRID-001
 * @title FindingsGrid: category-grouped grid of technique result cards
 * @status accepted
 * @rationale Grouping by category (diagnostic / contrarian / imaginative) lets
 *   analysts quickly see which analytical lens produced which findings, rather
 *   than a flat chronological list. Each category has a header with a count.
 *   The cards link to full technique detail. Categories with no results are
 *   omitted rather than shown as empty sections.
 */
import type { Artifact } from '../../api/types'
import TechniqueCard from './TechniqueCard'

interface FindingsGridProps {
  artifacts: Artifact[]
  runId: string
  summaries?: Record<string, string>  // technique_id -> summary text
}

const CATEGORY_ORDER = ['diagnostic', 'contrarian', 'imaginative'] as const
const CATEGORY_LABELS: Record<string, string> = {
  diagnostic: 'Diagnostic',
  contrarian: 'Contrarian',
  imaginative: 'Imaginative',
}

export default function FindingsGrid({ artifacts, runId, summaries = {} }: FindingsGridProps) {
  const byCategory = CATEGORY_ORDER.reduce<Record<string, Artifact[]>>((acc, cat) => {
    acc[cat] = artifacts.filter(a => a.category === cat)
    return acc
  }, {})

  const hasAny = artifacts.length > 0

  if (!hasAny) {
    return (
      <div className="findings-empty">
        <span className="text-muted text-sm">No technique results yet</span>
      </div>
    )
  }

  return (
    <div className="findings-grid">
      {CATEGORY_ORDER.filter(cat => byCategory[cat].length > 0).map(cat => (
        <div key={cat} className={`findings-category findings-category-${cat}`}>
          <div className="findings-category-header">
            <span className={`findings-category-label findings-category-label-${cat}`}>
              {CATEGORY_LABELS[cat]}
            </span>
            <span className="findings-category-count">
              {byCategory[cat].length}
            </span>
          </div>
          <div className="findings-category-cards">
            {byCategory[cat].map(artifact => (
              <TechniqueCard
                key={artifact.technique_id}
                artifact={artifact}
                runId={runId}
                summary={summaries[artifact.technique_id]}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

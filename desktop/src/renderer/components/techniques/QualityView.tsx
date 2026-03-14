import IntelCard from '../common/IntelCard'
import IntelBadge from '../common/IntelBadge'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

interface Source {
  source?: string
  name?: string
  reliability?: string
  credibility?: string
  type?: string
  limitations?: string
  [key: string]: any
}

function ReliabilityBadge({ level }: { level?: string }) {
  if (!level) return null
  const lvl = level.toLowerCase()
  const badgeLevel =
    lvl === 'high' || lvl === 'reliable' ? 'high'
      : lvl === 'medium' || lvl === 'moderate' ? 'medium'
      : 'low'
  return <IntelBadge label={level} variant="confidence" level={badgeLevel} />
}

export default function QualityView({ data }: TechniqueRendererProps) {
  const sources: Source[] = data?.sources || data?.source_reliability || []
  const gaps: string[] = data?.information_gaps || data?.gaps || []
  const strengths: string[] = data?.strengths || []
  const weaknesses: string[] = data?.weaknesses || data?.limitations || []

  return (
    <div className="technique-container">
      {data?.summary && (
        <IntelCard accent="cyan">
          <p className="text-secondary" style={{ margin: 0 }}>{data.summary}</p>
        </IntelCard>
      )}

      {data?.overall_quality && (
        <IntelCard title="Overall Quality Assessment" accent="cyan">
          <div className="quality-overall">
            <p className="text-secondary" style={{ margin: 0 }}>{data.overall_quality}</p>
            {data?.quality_rating && (
              <div style={{ marginTop: 8 }}>
                <ReliabilityBadge level={data.quality_rating} />
              </div>
            )}
          </div>
        </IntelCard>
      )}

      {sources.length > 0 && (
        <IntelCard title="Source Reliability" accent="green">
          <div className="intel-table-wrapper">
            <table className="intel-table">
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Reliability</th>
                  <th>Type</th>
                  <th>Limitations</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((s, i) => (
                  <tr key={i}>
                    <td>{s.source || s.name || '—'}</td>
                    <td>
                      <ReliabilityBadge level={s.reliability || s.credibility} />
                    </td>
                    <td className="text-secondary text-sm">{s.type || '—'}</td>
                    <td className="text-secondary text-sm">{s.limitations || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </IntelCard>
      )}

      <div className="technique-two-col">
        {strengths.length > 0 && (
          <IntelCard title="Strengths" accent="green">
            <ul className="technique-list">
              {strengths.map((s, i) => (
                <li key={i} className="technique-list-item technique-list-item-positive">
                  {s}
                </li>
              ))}
            </ul>
          </IntelCard>
        )}

        {weaknesses.length > 0 && (
          <IntelCard title="Weaknesses / Limitations" accent="amber">
            <ul className="technique-list">
              {weaknesses.map((w, i) => (
                <li key={i} className="technique-list-item technique-list-item-warning">
                  {w}
                </li>
              ))}
            </ul>
          </IntelCard>
        )}
      </div>

      {gaps.length > 0 && (
        <IntelCard title="Information Gaps" accent="red">
          <ul className="technique-list">
            {gaps.map((g, i) => (
              <li key={i} className="technique-list-item technique-list-item-gap">
                {g}
              </li>
            ))}
          </ul>
        </IntelCard>
      )}

      {data?.recommendations && (
        <CollapsibleSection title="Recommendations" defaultOpen={false}>
          {Array.isArray(data.recommendations)
            ? (
              <ul className="technique-list">
                {data.recommendations.map((r: string, i: number) => (
                  <li key={i} className="technique-list-item text-secondary">{r}</li>
                ))}
              </ul>
            )
            : <p className="text-secondary text-sm">{data.recommendations}</p>
          }
        </CollapsibleSection>
      )}
    </div>
  )
}

registerRenderer('quality', QualityView)

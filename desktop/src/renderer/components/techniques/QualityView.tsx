/**
 * @decision DEC-DESKTOP-QUALITY-001
 * @title QualityView: source table aligned to SourceQualityRow model fields
 * @status accepted
 * @rationale Fixed field name mismatches that caused 8-13% display rate. The model
 *   uses source_id (not source/name), source_type (not type), gaps (not limitations),
 *   overall_assessment (not overall_quality), key_gaps (not information_gaps/gaps list).
 *   Also added access_quality, corroboration, deception_indicators, and
 *   collection_requirements which were present in the model but never rendered.
 */
import IntelCard from '../common/IntelCard'
import IntelBadge from '../common/IntelBadge'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

interface SourceQualityRow {
  source_id: string
  description?: string
  source_type?: string
  reliability?: string
  access_quality?: string
  corroboration?: string
  gaps?: string
  [key: string]: any
}

function ReliabilityBadge({ level }: { level?: string }) {
  if (!level) return null
  const lvl = level.toLowerCase()
  const badgeLevel =
    lvl === 'high' ? 'high'
      : lvl === 'medium' ? 'medium'
      : 'low'
  return <IntelBadge label={level} variant="confidence" level={badgeLevel} />
}

export default function QualityView({ data }: TechniqueRendererProps) {
  const sources: SourceQualityRow[] = data?.sources || []
  const keyGaps: string[] = data?.key_gaps || []
  const deceptionIndicators: string[] = data?.deception_indicators || []
  const collectionRequirements: string[] = data?.collection_requirements || []

  return (
    <div className="technique-container">
      {data?.summary && (
        <IntelCard accent="cyan">
          <p className="text-secondary" style={{ margin: 0 }}>{data.summary}</p>
        </IntelCard>
      )}

      {data?.overall_assessment && (
        <IntelCard title="Overall Assessment" accent="cyan">
          <p className="text-secondary" style={{ margin: 0 }}>{data.overall_assessment}</p>
        </IntelCard>
      )}

      {sources.length > 0 && (
        <IntelCard title="Source Reliability" accent="green">
          <div className="intel-table-wrapper">
            <table className="intel-table">
              <thead>
                <tr>
                  <th>Source ID</th>
                  <th>Description</th>
                  <th>Type</th>
                  <th>Reliability</th>
                  <th>Access Quality</th>
                  <th>Corroboration</th>
                  <th>Gaps</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((s, i) => (
                  <tr key={i}>
                    <td className="text-sm" style={{ fontWeight: 600 }}>{s.source_id || '—'}</td>
                    <td className="text-secondary text-sm">{s.description || '—'}</td>
                    <td className="text-secondary text-sm">{s.source_type || '—'}</td>
                    <td>
                      <ReliabilityBadge level={s.reliability} />
                    </td>
                    <td className="text-secondary text-sm">{s.access_quality || '—'}</td>
                    <td className="text-secondary text-sm">{s.corroboration || '—'}</td>
                    <td className="text-secondary text-sm">{s.gaps || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </IntelCard>
      )}

      {keyGaps.length > 0 && (
        <IntelCard title="Key Gaps" accent="red">
          <ul className="technique-list">
            {keyGaps.map((g, i) => (
              <li key={i} className="technique-list-item technique-list-item-gap">
                {g}
              </li>
            ))}
          </ul>
        </IntelCard>
      )}

      {deceptionIndicators.length > 0 && (
        <IntelCard title="Deception Indicators" accent="amber">
          <ul className="technique-list">
            {deceptionIndicators.map((d, i) => (
              <li key={i} className="technique-list-item technique-list-item-warning">
                {d}
              </li>
            ))}
          </ul>
        </IntelCard>
      )}

      {collectionRequirements.length > 0 && (
        <CollapsibleSection title="Collection Requirements" defaultOpen={false}>
          <ul className="technique-list">
            {collectionRequirements.map((r, i) => (
              <li key={i} className="technique-list-item text-secondary">{r}</li>
            ))}
          </ul>
        </CollapsibleSection>
      )}
    </div>
  )
}

registerRenderer('quality', QualityView)

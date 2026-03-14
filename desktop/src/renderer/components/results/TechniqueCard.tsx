/**
 * @decision DEC-DESKTOP-TECHNIQUE-CARD-001
 * @title TechniqueCard: summary card that navigates to full technique detail
 * @status accepted
 * @rationale The findings grid needs a compact representation of each technique
 *   result. 200-char truncation preserves context while keeping cards uniform.
 *   Navigation to the full detail page is the primary action — the card is a
 *   preview, not the complete view.
 */
import { useNavigate } from 'react-router'
import IntelBadge from '../common/IntelBadge'
import type { Artifact } from '../../api/types'

interface TechniqueCardProps {
  artifact: Artifact
  runId: string
  summary?: string
}

export default function TechniqueCard({ artifact, runId, summary }: TechniqueCardProps) {
  const navigate = useNavigate()
  const category = artifact.category as 'diagnostic' | 'contrarian' | 'imaginative'

  const truncatedSummary = summary
    ? summary.length > 200 ? summary.slice(0, 197) + '...' : summary
    : null

  return (
    <div
      className={`technique-result-card technique-result-card-${category}`}
      onClick={() => navigate(`/runs/${runId}/techniques/${artifact.technique_id}`)}
      role="button"
      tabIndex={0}
      onKeyDown={e => e.key === 'Enter' && navigate(`/runs/${runId}/techniques/${artifact.technique_id}`)}
    >
      <div className="technique-result-card-header">
        <span className="technique-result-card-name">{artifact.technique_name}</span>
        <IntelBadge
          label={category}
          variant="category"
          category={category}
        />
      </div>
      {truncatedSummary && (
        <p className="technique-result-card-summary">{truncatedSummary}</p>
      )}
      <span className="technique-result-card-cta">View full analysis →</span>
    </div>
  )
}

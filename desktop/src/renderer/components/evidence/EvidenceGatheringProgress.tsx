/**
 * @decision DEC-DESKTOP-EVIDENCE-PROGRESS-001
 * @title EvidenceGatheringProgress: real-time provider status during evidence gathering
 * @status accepted
 * @rationale Reuses the provider status dot pattern from RunDetail to show which research
 *   providers are running, completed, or failed. Provides visual feedback during the
 *   potentially long research phase.
 *
 * @decision DEC-DESKTOP-EVIDENCE-PROGRESS-002
 * @title Human-readable event labels replace raw camelCase conversion
 * @status accepted
 * @rationale Raw camelCase→spaced conversion ("Provider Started") was unhelpful to users.
 *   A mapping to action-oriented labels ("Searching via perplexity...") communicates what
 *   the system is doing. Provider completion now shows source counts. Footer shows provider
 *   completion progress ("2 of 4 providers complete") instead of an opaque event count.
 */
import type { EvidenceGatheringProgress, PipelineEventMessage } from '../../api/types'

interface Props {
  progress: EvidenceGatheringProgress
}

/** Map a pipeline event to a human-readable status label. */
function eventLabel(event: PipelineEventMessage): string {
  const { type, data } = event
  switch (type) {
    case 'ResearchStarted':
      return 'Querying research providers...'
    case 'ProviderStarted':
      return `Searching via ${data.name}...`
    case 'ProviderCompleted':
      return `${data.name} complete — ${data.citation_count} sources`
    case 'ProviderFailed':
      return `${data.name} failed`
    case 'StageStarted':
      if (data.stage === 'decomposition') return 'Decomposing evidence...'
      if (data.stage === 'structuring') return 'Structuring claims...'
      break
    case 'EvidenceGatheringCompleted':
      return `Complete — ${data.item_count} items from ${data.source_count} sources`
    default:
      break
  }
  // Fallback: camelCase → spaced
  return type.replace(/([A-Z])/g, ' $1').trim()
}

export default function EvidenceGatheringProgress({ progress }: Props) {
  const { researchProviders, events } = progress

  const latestEvent = events.length > 0 ? events[events.length - 1] : null
  const latestLabel = latestEvent ? eventLabel(latestEvent) : 'Initializing...'

  const providerEntries = Object.entries(researchProviders)

  const completedCount = providerEntries.filter(
    ([, s]) => s === 'completed' || s === 'failed',
  ).length

  return (
    <div className="evidence-gathering">
      <div className="evidence-gathering-title">Gathering Evidence...</div>

      {/* Spinner */}
      <div style={{ marginBottom: 20 }}>
        <div
          style={{
            width: 32,
            height: 32,
            border: '3px solid var(--color-border-subtle)',
            borderTopColor: 'var(--color-signal-cyan)',
            borderRadius: '50%',
            animation: 'spin 0.8s linear infinite',
            margin: '0 auto',
          }}
        />
      </div>

      {/* Latest event label */}
      <div className="text-xs text-muted" style={{ marginBottom: 20 }}>
        {latestLabel}
      </div>

      {/* Provider status list */}
      {providerEntries.length > 0 && (
        <div className="evidence-provider-list">
          {providerEntries.map(([name, status]) => (
            <div key={name} className="evidence-provider-row">
              <div className={`evidence-provider-dot ${status}`} />
              <span className="evidence-provider-name">{name}</span>
              <span className="evidence-provider-status">{status}</span>
            </div>
          ))}
        </div>
      )}

      {/* Provider completion summary */}
      {providerEntries.length > 0 && (
        <div className="text-xs text-muted" style={{ marginTop: 16 }}>
          {completedCount} of {providerEntries.length} provider
          {providerEntries.length !== 1 ? 's' : ''} complete
        </div>
      )}

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}

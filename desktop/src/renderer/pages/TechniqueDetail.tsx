/**
 * @decision DEC-DESKTOP-TECHNIQUE-DETAIL-001
 * @title TechniqueDetail: renderer-registry dispatch with JSON fallback
 * @status accepted
 * @rationale Each technique produces distinct JSON. A registry maps technique_id
 *   to a specialized React component. Unknown techniques fall back to a formatted
 *   JSON dump — this ensures we never crash on new techniques and gives analysts
 *   raw data access during development. The artifact path comes from the RunDetail
 *   API response; we fetch the JSON via getRunArtifact. Category context (diagnostic/
 *   contrarian/imaginative) is loaded from the techniques list and used for the
 *   accent color in the page header.
 */
import { useParams, useNavigate } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { useApiContext } from '../api/context'
import { SatClient } from '../api/client'
import { useRun } from '../hooks/useRuns'
import { useTechniques } from '../hooks/useTechniques'
import IntelCard from '../components/common/IntelCard'
import IntelBadge from '../components/common/IntelBadge'

// Import all renderers to trigger registration side-effects
import { getRenderer } from '../components/techniques/index'

const CATEGORY_ACCENT: Record<string, 'green' | 'amber' | 'purple'> = {
  diagnostic: 'green',
  contrarian: 'amber',
  imaginative: 'purple',
}

function LoadingState() {
  return (
    <div className="technique-detail-loading">
      <div className="skeleton-card" />
      <div className="skeleton-card skeleton-card-tall" />
    </div>
  )
}

function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <IntelCard accent="red" title="Error Loading Technique">
      <p className="text-secondary text-sm">{message}</p>
      {onRetry && (
        <button className="btn-retry" onClick={onRetry}>
          Retry
        </button>
      )}
    </IntelCard>
  )
}

function JsonFallback({ data }: { data: any }) {
  return (
    <IntelCard title="Raw JSON Output" accent="cyan">
      <p className="text-muted text-xs" style={{ marginBottom: 8 }}>
        No specialized renderer for this technique — showing raw output.
      </p>
      <pre className="ach-json-fallback">{JSON.stringify(data, null, 2)}</pre>
    </IntelCard>
  )
}

export default function TechniqueDetail() {
  const { runId, techniqueId } = useParams<{ runId: string; techniqueId: string }>()
  const navigate = useNavigate()
  const { baseUrl } = useApiContext()

  const { data: run, isLoading: runLoading, error: runError } = useRun(runId)
  const { data: techniques } = useTechniques()

  // Find the artifact for this technique
  const artifact = run?.artifacts?.find((a) => a.technique_id === techniqueId)

  // Fetch JSON artifact
  const {
    data: artifactData,
    isLoading: artifactLoading,
    error: artifactError,
    refetch,
  } = useQuery({
    queryKey: ['artifact', runId, techniqueId, artifact?.json_path],
    queryFn: () =>
      new SatClient(baseUrl!).getRunArtifact(runId!, artifact!.json_path!),
    enabled: !!baseUrl && !!runId && !!artifact?.json_path,
  })

  const isLoading = runLoading || artifactLoading

  // Resolve category and accent
  const techniqueInfo = techniques?.find((t) => t.id === techniqueId)
  const category = techniqueInfo?.category || (artifact?.category as string) || 'diagnostic'
  const accent: 'green' | 'amber' | 'purple' = CATEGORY_ACCENT[category] ?? 'green'
  const techniqueName =
    techniqueInfo?.name || artifact?.technique_name || techniqueId || '—'

  if (isLoading) return <LoadingState />

  if (runError) {
    return (
      <ErrorState
        message={`Failed to load run: ${(runError as Error).message}`}
        onRetry={() => refetch()}
      />
    )
  }

  if (artifactError) {
    return (
      <ErrorState
        message={`Failed to load artifact: ${(artifactError as Error).message}`}
        onRetry={() => refetch()}
      />
    )
  }

  // Look up a specialized renderer
  const Renderer = techniqueId ? getRenderer(techniqueId) : null

  return (
    <div className="technique-detail">
      {/* Header */}
      <div className="technique-detail-header">
        <button
          className="btn-back"
          onClick={() => navigate(`/runs/${runId}`)}
        >
          ← Back to Run
        </button>
        <div className="technique-detail-title-row">
          <h2 className="technique-detail-title">{techniqueName}</h2>
          <IntelBadge
            label={category}
            variant="category"
            category={category as 'diagnostic' | 'contrarian' | 'imaginative'}
          />
          {artifact?.json_path && baseUrl && (
            <button
              className="btn-secondary"
              style={{ marginLeft: 'auto' }}
              onClick={() => {
                new SatClient(baseUrl).downloadArtifact(runId!, artifact.json_path!).then(blob => {
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url
                  a.download = `${techniqueId}-${runId}.json`
                  a.click()
                  URL.revokeObjectURL(url)
                })
              }}
            >
              Download JSON
            </button>
          )}
        </div>
        {techniqueInfo?.description && (
          <p className="technique-detail-desc text-secondary text-sm">
            {techniqueInfo.description}
          </p>
        )}
      </div>

      {/* No artifact found */}
      {!artifact && !isLoading && (
        <IntelCard title="No Artifact" accent="amber">
          <p className="text-secondary text-sm">
            No artifact found for technique <code>{techniqueId}</code> in run{' '}
            <code>{runId}</code>.
          </p>
        </IntelCard>
      )}

      {/* No JSON path */}
      {artifact && !artifact.json_path && (
        <IntelCard title="Text-Only Output" accent={accent}>
          <p className="text-secondary text-sm">
            This technique produced a markdown artifact only. View the full report
            for formatted output.
          </p>
        </IntelCard>
      )}

      {/* Render the data */}
      {artifactData && (
        <>
          {Renderer ? (
            <Renderer
              data={artifactData}
              techniqueId={techniqueId || ''}
              techniqueName={techniqueName}
            />
          ) : (
            <JsonFallback data={artifactData} />
          )}
        </>
      )}
    </div>
  )
}

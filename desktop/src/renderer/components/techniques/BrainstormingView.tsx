/**
 * @decision DEC-DESKTOP-BRAINSTORM-001
 * @title BrainstormingView: renders BrainstormingResult with Idea objects and cluster significance
 * @status accepted
 * @rationale Brainstorming produces Idea objects (id, text, source_rationale), not plain
 *   strings. The renderer must access idea.text for display and optionally show
 *   idea.source_rationale as provenance context. Cluster significance is displayed
 *   below each cluster's ideas to explain why the cluster matters. The focal_question
 *   anchors the session at the top, and divergent_ideas provides a raw unfiltered view
 *   before clustering.
 */
import IntelCard from '../common/IntelCard'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

interface Idea {
  id?: string
  text?: string
  source_rationale?: string
}

interface IdeaCluster {
  name?: string
  ideas?: Idea[]
  significance?: string
}

function IdeaClusterCard({ cluster, idx }: { cluster: IdeaCluster; idx: number }) {
  const accents = ['cyan', 'green', 'amber', 'purple', 'red'] as const
  const accent = accents[idx % accents.length]
  const title = cluster.name || `Cluster ${idx + 1}`
  const ideas: Idea[] = cluster.ideas || []

  return (
    <IntelCard title={title} accent={accent}>
      {ideas.length > 0 && (
        <ul className="technique-list">
          {ideas.map((idea, i) => (
            <li key={i} className="technique-list-item text-secondary">
              <span>{idea.text || String(idea)}</span>
              {idea.source_rationale && (
                <span className="text-muted text-xs" style={{ display: 'block', marginTop: '0.15rem', fontStyle: 'italic' }}>
                  {idea.source_rationale}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {cluster.significance && (
        <p className="text-secondary text-sm" style={{ marginTop: '0.5rem', marginBottom: 0, borderTop: '1px solid var(--border-subtle, rgba(255,255,255,0.06))', paddingTop: '0.5rem' }}>
          <span style={{ fontWeight: 600 }}>Significance: </span>
          {cluster.significance}
        </p>
      )}
    </IntelCard>
  )
}

export default function BrainstormingView({ data }: TechniqueRendererProps) {
  const focalQuestion: string = data?.focal_question || ''
  const divergentIdeas: Idea[] = data?.divergent_ideas || []
  const clusters: IdeaCluster[] = data?.clusters || []
  const priorityAreas: string[] = data?.priority_areas || []
  const unconventional: string[] = data?.unconventional_insights || []

  return (
    <div className="technique-container">
      {data?.summary && (
        <IntelCard accent="purple">
          <p className="text-secondary" style={{ margin: 0 }}>{data.summary}</p>
        </IntelCard>
      )}

      {/* Focal question anchors the session */}
      {focalQuestion && (
        <IntelCard title="Focal Question" accent="amber">
          <p className="text-secondary" style={{ margin: 0, fontStyle: 'italic' }}>{focalQuestion}</p>
        </IntelCard>
      )}

      {/* Priority areas up front */}
      {priorityAreas.length > 0 && (
        <IntelCard title="Priority Areas" accent="amber">
          <ul className="technique-list">
            {priorityAreas.map((area, i) => (
              <li key={i} className="technique-list-item technique-list-item-warning">{area}</li>
            ))}
          </ul>
        </IntelCard>
      )}

      {/* Idea clusters */}
      {clusters.length > 0 && (
        <div className="brainstorming-clusters">
          {clusters.map((cluster, i) => (
            <IdeaClusterCard key={i} cluster={cluster} idx={i} />
          ))}
        </div>
      )}

      {/* Raw divergent ideas (shown when no clusters, or as a collapsible section) */}
      {divergentIdeas.length > 0 && clusters.length === 0 && (
        <IntelCard title="All Ideas" accent="purple">
          <ul className="technique-list">
            {divergentIdeas.map((idea, i) => (
              <li key={i} className="technique-list-item text-secondary">
                <span>{idea.text || String(idea)}</span>
                {idea.source_rationale && (
                  <span className="text-muted text-xs" style={{ display: 'block', marginTop: '0.15rem', fontStyle: 'italic' }}>
                    {idea.source_rationale}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </IntelCard>
      )}

      {/* Divergent ideas as collapsible when clusters exist */}
      {divergentIdeas.length > 0 && clusters.length > 0 && (
        <CollapsibleSection title={`All Raw Ideas (${divergentIdeas.length})`} defaultOpen={false}>
          <ul className="technique-list">
            {divergentIdeas.map((idea, i) => (
              <li key={i} className="technique-list-item text-secondary">
                <span>{idea.text || String(idea)}</span>
                {idea.source_rationale && (
                  <span className="text-muted text-xs" style={{ display: 'block', marginTop: '0.15rem', fontStyle: 'italic' }}>
                    {idea.source_rationale}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </CollapsibleSection>
      )}

      {/* Unconventional insights */}
      {unconventional.length > 0 && (
        <IntelCard title="Unconventional Insights" accent="purple">
          <ul className="technique-list">
            {unconventional.map((insight, i) => (
              <li key={i} className="technique-list-item technique-list-item-insight">{insight}</li>
            ))}
          </ul>
        </IntelCard>
      )}
    </div>
  )
}

registerRenderer('brainstorming', BrainstormingView)

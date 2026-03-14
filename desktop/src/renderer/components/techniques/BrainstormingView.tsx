import IntelCard from '../common/IntelCard'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

interface IdeaCluster {
  cluster?: string
  theme?: string
  name?: string
  ideas?: string[]
  items?: string[]
  [key: string]: any
}

function IdeaClusterCard({ cluster, idx }: { cluster: IdeaCluster; idx: number }) {
  const accents = ['cyan', 'green', 'amber', 'purple', 'red'] as const
  const accent = accents[idx % accents.length]
  const title = cluster.cluster || cluster.theme || cluster.name || `Cluster ${idx + 1}`
  const ideas: string[] = cluster.ideas || cluster.items || []

  return (
    <IntelCard title={title} accent={accent}>
      {ideas.length > 0
        ? (
          <ul className="technique-list">
            {ideas.map((idea, i) => (
              <li key={i} className="technique-list-item text-secondary">{idea}</li>
            ))}
          </ul>
        )
        : (
          <p className="text-secondary text-sm">
            {typeof cluster === 'string' ? cluster : '—'}
          </p>
        )}
    </IntelCard>
  )
}

export default function BrainstormingView({ data }: TechniqueRendererProps) {
  const clusters: IdeaCluster[] =
    data?.clusters || data?.idea_clusters || data?.themes || []
  const priorityAreas: string[] =
    data?.priority_areas || data?.high_priority || []
  const unconventional: string[] =
    data?.unconventional_insights || data?.novel_ideas || data?.unexpected || []
  const allIdeas: string[] =
    data?.all_ideas || data?.ideas || []

  return (
    <div className="technique-container">
      {data?.summary && (
        <IntelCard accent="purple">
          <p className="text-secondary" style={{ margin: 0 }}>{data.summary}</p>
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

      {/* Flat idea list (if no clusters) */}
      {clusters.length === 0 && allIdeas.length > 0 && (
        <IntelCard title="All Ideas" accent="purple">
          <ul className="technique-list">
            {allIdeas.map((idea, i) => (
              <li key={i} className="technique-list-item text-secondary">{idea}</li>
            ))}
          </ul>
        </IntelCard>
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

      {data?.next_steps && (
        <CollapsibleSection title="Recommended Next Steps" defaultOpen={false}>
          {Array.isArray(data.next_steps)
            ? (
              <ul className="technique-list">
                {data.next_steps.map((s: string, i: number) => (
                  <li key={i} className="technique-list-item text-secondary">{s}</li>
                ))}
              </ul>
            )
            : <p className="text-secondary text-sm">{data.next_steps}</p>
          }
        </CollapsibleSection>
      )}
    </div>
  )
}

registerRenderer('brainstorming', BrainstormingView)

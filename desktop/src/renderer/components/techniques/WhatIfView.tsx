/**
 * @decision DEC-DESKTOP-WHATIF-001
 * @title WhatIfView: renders WhatIfResult with backward-reasoning chain of argumentation
 * @status accepted
 * @rationale The What If? technique constructs scenarios by assuming an event has
 *   occurred and reasoning backward. The centerpiece is the chain_of_argumentation
 *   (list of ScenarioStep objects with step_number, description, enabling_factors).
 *   Each step is displayed with its enabling factors so the reader can trace the
 *   logic from triggering events through to the assumed outcome. The backward_reasoning
 *   field captures the reflective backward pass; alternative_pathways and indicators
 *   extend the analysis beyond the primary chain.
 */
import IntelCard from '../common/IntelCard'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

interface ScenarioStep {
  step_number?: number
  description?: string
  enabling_factors?: string[]
}

function ChainOfArgumentation({ steps }: { steps: ScenarioStep[] }) {
  return (
    <div className="whatif-chain">
      {steps.map((step, i) => (
        <div key={i} className="whatif-chain-step">
          <div className="whatif-step-node">{step.step_number ?? i + 1}</div>
          <div className="whatif-step-content">
            <p className="text-secondary text-sm" style={{ margin: 0 }}>
              {step.description || String(step)}
            </p>
            {step.enabling_factors && step.enabling_factors.length > 0 && (
              <ul className="technique-list" style={{ marginTop: '0.4rem' }}>
                {step.enabling_factors.map((factor, fi) => (
                  <li key={fi} className="technique-list-item text-secondary" style={{ fontSize: '0.8rem' }}>
                    {factor}
                  </li>
                ))}
              </ul>
            )}
          </div>
          {i < steps.length - 1 && <div className="whatif-step-arrow">↓</div>}
        </div>
      ))}
    </div>
  )
}

export default function WhatIfView({ data }: TechniqueRendererProps) {
  const assumedEvent: string = data?.assumed_event || ''
  const conventionalView: string = data?.conventional_view || ''
  const triggeringEvents: string[] = data?.triggering_events || []
  const chainOfArgumentation: ScenarioStep[] = data?.chain_of_argumentation || []
  const backwardReasoning: string = data?.backward_reasoning || ''
  const alternativePathways: string[] = data?.alternative_pathways || []
  const indicators: string[] = data?.indicators || []
  const consequences: string = data?.consequences || ''
  const probabilityReassessment: string = data?.probability_reassessment || ''

  return (
    <div className="technique-container">
      {data?.summary && (
        <IntelCard accent="purple">
          <p className="text-secondary" style={{ margin: 0 }}>{data.summary}</p>
        </IntelCard>
      )}

      {/* The assumed event */}
      {assumedEvent && (
        <IntelCard title="Assumed Event" accent="amber">
          <p className="whatif-event">{assumedEvent}</p>
        </IntelCard>
      )}

      {/* Why this event is considered unlikely */}
      {conventionalView && (
        <IntelCard title="Conventional View" accent="cyan">
          <p className="text-secondary" style={{ margin: 0 }}>{conventionalView}</p>
        </IntelCard>
      )}

      {/* Triggering events that set the scenario in motion */}
      {triggeringEvents.length > 0 && (
        <IntelCard title="Triggering Events" accent="cyan">
          <ul className="technique-list">
            {triggeringEvents.map((event, i) => (
              <li key={i} className="technique-list-item text-secondary">{event}</li>
            ))}
          </ul>
        </IntelCard>
      )}

      {/* The backward reasoning chain of argumentation — centerpiece */}
      {chainOfArgumentation.length > 0 && (
        <IntelCard title="Chain of Argumentation (Backward Reasoning)" accent="purple">
          <ChainOfArgumentation steps={chainOfArgumentation} />
        </IntelCard>
      )}

      {/* Backward reasoning narrative */}
      {backwardReasoning && (
        <IntelCard title="Backward Reasoning" accent="purple">
          <p className="text-secondary" style={{ margin: 0 }}>{backwardReasoning}</p>
        </IntelCard>
      )}

      {/* Alternative pathways to the same outcome */}
      {alternativePathways.length > 0 && (
        <IntelCard title="Alternative Pathways" accent="green">
          <ul className="technique-list">
            {alternativePathways.map((pathway, i) => (
              <li key={i} className="technique-list-item text-secondary">{pathway}</li>
            ))}
          </ul>
        </IntelCard>
      )}

      {/* Warning signs */}
      {indicators.length > 0 && (
        <IntelCard title="Indicators (Warning Signs)" accent="amber">
          <ul className="technique-list">
            {indicators.map((indicator, i) => (
              <li key={i} className="technique-list-item text-secondary">{indicator}</li>
            ))}
          </ul>
        </IntelCard>
      )}

      {/* Consequences */}
      {consequences && (
        <IntelCard title="Consequences" accent="green">
          <p className="text-secondary" style={{ margin: 0 }}>{consequences}</p>
        </IntelCard>
      )}

      {/* How the exercise changes likelihood assessment */}
      {probabilityReassessment && (
        <CollapsibleSection title="Probability Reassessment" defaultOpen={false}>
          <p className="text-secondary text-sm">{probabilityReassessment}</p>
        </CollapsibleSection>
      )}
    </div>
  )
}

registerRenderer('what_if', WhatIfView)

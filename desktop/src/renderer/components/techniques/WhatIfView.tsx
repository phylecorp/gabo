import IntelCard from '../common/IntelCard'
import CollapsibleSection from '../common/CollapsibleSection'
import { registerRenderer } from './rendererRegistry'
import type { TechniqueRendererProps } from './rendererRegistry'

interface CausalStep {
  step?: string
  event?: string
  description?: string
  condition?: string
  [key: string]: any
}

function CausalChain({ steps }: { steps: CausalStep[] }) {
  return (
    <div className="whatif-chain">
      {steps.map((step, i) => (
        <div key={i} className="whatif-chain-step">
          <div className="whatif-step-node">{i + 1}</div>
          <div className="whatif-step-content">
            <p className="text-secondary text-sm" style={{ margin: 0 }}>
              {step.step || step.event || step.description || step.condition || String(step)}
            </p>
          </div>
          {i < steps.length - 1 && <div className="whatif-step-arrow">↓</div>}
        </div>
      ))}
    </div>
  )
}

export default function WhatIfView({ data }: TechniqueRendererProps) {
  const assumedEvent: string =
    data?.assumed_event || data?.what_if_event || data?.scenario || ''
  const causalChain: CausalStep[] =
    data?.causal_chain || data?.chain_of_causation || data?.steps || []
  const requiredConditions: string[] =
    data?.required_conditions || data?.conditions || data?.prerequisites || []
  const implications: string[] =
    data?.implications || data?.consequences || []

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

      {/* Backward reasoning chain */}
      {causalChain.length > 0 && (
        <IntelCard title="Chain of Causation (Backward Reasoning)" accent="purple">
          <CausalChain steps={causalChain} />
        </IntelCard>
      )}

      {/* Required conditions */}
      {requiredConditions.length > 0 && (
        <IntelCard title="Required Conditions" accent="cyan">
          <ul className="technique-list">
            {requiredConditions.map((cond, i) => (
              <li key={i} className="technique-list-item text-secondary">{cond}</li>
            ))}
          </ul>
        </IntelCard>
      )}

      {/* Implications */}
      {implications.length > 0 && (
        <IntelCard title="Implications" accent="green">
          <ul className="technique-list">
            {implications.map((imp, i) => (
              <li key={i} className="technique-list-item text-secondary">{imp}</li>
            ))}
          </ul>
        </IntelCard>
      )}

      {data?.probability_assessment && (
        <CollapsibleSection title="Probability Assessment" defaultOpen={false}>
          <p className="text-secondary text-sm">{data.probability_assessment}</p>
        </CollapsibleSection>
      )}
    </div>
  )
}

registerRenderer('what_if', WhatIfView)

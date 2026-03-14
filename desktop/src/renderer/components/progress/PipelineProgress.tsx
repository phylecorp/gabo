/**
 * @decision DEC-DESKTOP-PIPELINE-PROGRESS-001
 * @title PipelineProgress: horizontal node-line pipeline visualization
 * @status accepted
 * @rationale The pipeline has a fixed DAG shape: optional research → ordered
 *   techniques → synthesis. A horizontal node-line diagram makes the sequence
 *   and status immediately readable without scrolling. Each node pulses when
 *   active (CSS animation), turns green on completion, red on failure. The
 *   component is pure-display: it derives its state from RunProgress events,
 *   not internal state, so it re-renders correctly from any parent.
 */
import type { RunProgress } from '../../api/types'

interface Stage {
  id: string
  label: string
  kind: 'research' | 'technique' | 'synthesis'
}

interface PipelineProgressProps {
  stages: Stage[]
  progress: RunProgress
}

function getNodeStatus(
  stage: Stage,
  progress: RunProgress
): 'pending' | 'active' | 'completed' | 'failed' {
  if (progress.status === 'failed' && progress.currentStage === stage.id) return 'failed'

  // Research special-casing
  if (stage.kind === 'research') {
    if (progress.completedStages.includes('research')) return 'completed'
    if (progress.currentStage === 'research') return 'active'
    return 'pending'
  }

  // Synthesis
  if (stage.kind === 'synthesis') {
    if (progress.status === 'completed') return 'completed'
    if (progress.completedStages.some(s => s.startsWith('synthesis'))) return 'completed'
    if (progress.currentStage === 'synthesis' || progress.currentTechnique === stage.id) return 'active'
    return 'pending'
  }

  // Technique
  if (progress.completedStages.some(s => s.includes(stage.id))) return 'completed'
  if (progress.currentTechnique === stage.id) return 'active'
  return 'pending'
}

const STATUS_CLASS: Record<string, string> = {
  pending: 'pipeline-node-pending',
  active: 'pipeline-node-active',
  completed: 'pipeline-node-completed',
  failed: 'pipeline-node-failed',
}

const STATUS_SYMBOL: Record<string, string> = {
  pending: '○',
  active: '◉',
  completed: '●',
  failed: '✗',
}

export default function PipelineProgress({ stages, progress }: PipelineProgressProps) {
  return (
    <div className="pipeline-progress">
      <div className="pipeline-track">
        {stages.map((stage, i) => {
          const status = getNodeStatus(stage, progress)
          return (
            <div key={stage.id} className="pipeline-step">
              <div className={`pipeline-node ${STATUS_CLASS[status]}`}>
                <span className="pipeline-node-symbol">{STATUS_SYMBOL[status]}</span>
              </div>
              <span className={`pipeline-node-label ${status === 'active' ? 'pipeline-label-active' : ''}`}>
                {stage.label}
              </span>
              {i < stages.length - 1 && (
                <div className={`pipeline-connector ${status === 'completed' ? 'pipeline-connector-done' : ''}`} />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export type { Stage }

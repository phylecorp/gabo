/**
 * @decision DEC-DESKTOP-SYNTHESIS-PANEL-001
 * @title SynthesisPanel: bottom-line-first synthesis display
 * @status accepted
 * @rationale Intelligence products are bottom-line-up-front (BLUF). The bottom
 *   line assessment leads the panel at large text. Key findings with confidence
 *   badges follow. Convergent/divergent judgments in two columns surface where
 *   techniques agreed vs. where they produced conflicting signals — that's the
 *   analytical value of multi-technique analysis. Uncertainties and gaps are
 *   demoted to the bottom since they are actionable future tasking, not the
 *   primary analytical product.
 *
 * @decision DEC-DESKTOP-SYNTHESIS-PANEL-002
 * @title All sections below BLA collapse by default (BLUF-first display)
 * @status accepted
 * @rationale The BLA IS the BLUF — it must be immediately visible and scannable.
 *   All detail sections (key findings, convergent/divergent judgments, confidence
 *   assessments, uncertainties, gaps, next steps) are collapsed by default so the
 *   reader sees the bottom line without visual clutter. Users who want detail expand
 *   sections selectively. This matches how a policymaker reads an intelligence brief:
 *   bottom line first, supporting detail on demand.
 */
import type { SynthesisResult, TechniqueFinding } from '../../api/types'
import IntelBadge from '../common/IntelBadge'
import CollapsibleSection from '../common/CollapsibleSection'

interface SynthesisPanelProps {
  synthesis: SynthesisResult
}

function confidenceLevel(c: string): 'high' | 'medium' | 'low' {
  const lower = c.toLowerCase()
  if (lower === 'high') return 'high'
  if (lower === 'low') return 'low'
  return 'medium'
}

export default function SynthesisPanel({ synthesis }: SynthesisPanelProps) {
  return (
    <div className="synthesis-panel">
      <div className="synthesis-bla">
        <div className="synthesis-bla-label">Bottom Line Assessment</div>
        <p className="synthesis-bla-text">{synthesis.bottom_line_assessment}</p>
      </div>

      {synthesis.key_findings.length > 0 && (
        <CollapsibleSection title="Key Findings" count={synthesis.key_findings.length} defaultOpen={false}>
          <div className="synthesis-findings-list">
            {synthesis.key_findings.map((f: TechniqueFinding, i: number) => (
              <div key={i} className="synthesis-finding-row">
                <IntelBadge
                  label={f.confidence}
                  variant="confidence"
                  level={confidenceLevel(f.confidence)}
                />
                <span className="synthesis-finding-source text-muted text-xs font-mono">
                  {f.technique_name}
                </span>
                <span className="synthesis-finding-text">{f.key_finding}</span>
              </div>
            ))}
          </div>
        </CollapsibleSection>
      )}

      {synthesis.convergent_judgments.length > 0 && (
        <CollapsibleSection title="Convergent Judgments" count={synthesis.convergent_judgments.length} defaultOpen={false}>
          <ul className="synthesis-list">
            {synthesis.convergent_judgments.map((j, i) => (
              <li key={i} className="synthesis-list-item synthesis-list-item-green">{j}</li>
            ))}
          </ul>
        </CollapsibleSection>
      )}

      {synthesis.divergent_signals.length > 0 && (
        <CollapsibleSection title="Divergent Signals" count={synthesis.divergent_signals.length} defaultOpen={false}>
          <ul className="synthesis-list">
            {synthesis.divergent_signals.map((s, i) => (
              <li key={i} className="synthesis-list-item synthesis-list-item-amber">{s}</li>
            ))}
          </ul>
        </CollapsibleSection>
      )}

      {synthesis.highest_confidence_assessments.length > 0 && (
        <CollapsibleSection title="Highest Confidence Assessments" count={synthesis.highest_confidence_assessments.length} defaultOpen={false}>
          <ul className="synthesis-list">
            {synthesis.highest_confidence_assessments.map((a, i) => (
              <li key={i} className="synthesis-list-item synthesis-list-item-green">{a}</li>
            ))}
          </ul>
        </CollapsibleSection>
      )}

      {synthesis.remaining_uncertainties.length > 0 && (
        <CollapsibleSection title="Remaining Uncertainties" count={synthesis.remaining_uncertainties.length} defaultOpen={false}>
          <ul className="synthesis-list">
            {synthesis.remaining_uncertainties.map((u, i) => (
              <li key={i} className="synthesis-list-item synthesis-list-item-muted">{u}</li>
            ))}
          </ul>
        </CollapsibleSection>
      )}

      {synthesis.intelligence_gaps.length > 0 && (
        <CollapsibleSection title="Intelligence Gaps" count={synthesis.intelligence_gaps.length} defaultOpen={false}>
          <ul className="synthesis-list">
            {synthesis.intelligence_gaps.map((g, i) => (
              <li key={i} className="synthesis-list-item synthesis-list-item-amber">{g}</li>
            ))}
          </ul>
        </CollapsibleSection>
      )}

      {synthesis.recommended_next_steps.length > 0 && (
        <CollapsibleSection title="Recommended Next Steps" count={synthesis.recommended_next_steps.length} defaultOpen={false}>
          <ul className="synthesis-list">
            {synthesis.recommended_next_steps.map((s, i) => (
              <li key={i} className="synthesis-list-item synthesis-list-item-cyan">{s}</li>
            ))}
          </ul>
        </CollapsibleSection>
      )}
    </div>
  )
}

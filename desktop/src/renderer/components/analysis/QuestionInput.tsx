/**
 * @decision DEC-DESKTOP-QUESTION-INPUT-001
 * @title QuestionInput: prominent textarea with live character count
 * @status accepted
 * @rationale The question is the most critical input in the analysis workflow.
 *   It gets a large, visually prominent textarea to signal its importance.
 *   Character count is shown live so analysts know how much context they've
 *   provided without triggering token-limit surprises downstream.
 */
interface QuestionInputProps {
  value: string
  onChange: (value: string) => void
  disabled?: boolean
}

export default function QuestionInput({ value, onChange, disabled = false }: QuestionInputProps) {
  return (
    <div className="question-input-wrapper">
      <label className="question-input-label">
        Intelligence Question
        <span className="question-input-required">*</span>
      </label>
      <textarea
        className="question-input-textarea"
        placeholder="What is the likelihood that...? / Assess the probability of...? / Evaluate the threat posed by..."
        value={value}
        onChange={e => onChange(e.target.value)}
        disabled={disabled}
        rows={4}
        autoFocus
      />
      <div className="question-input-meta">
        <span className="question-input-hint">
          Frame as an analytical question. Be specific about the actor, action, and timeframe.
        </span>
        <span className={`question-input-count ${value.length > 800 ? 'question-input-count-warn' : ''}`}>
          {value.length} chars
        </span>
      </div>
    </div>
  )
}

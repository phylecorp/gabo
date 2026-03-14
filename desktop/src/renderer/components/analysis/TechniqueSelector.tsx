/**
 * @decision DEC-DESKTOP-TECHNIQUE-SELECTOR-001
 * @title TechniqueSelector: 3-column grid grouped by category with toggle cards
 * @status accepted
 * @rationale Techniques are grouped into three distinct analytical categories.
 *   The 3-column layout makes each category visually parallel, reinforcing that
 *   the analyst is building a multi-perspective picture. Each card is a full toggle
 *   (not a checkbox) so the affordance is obvious — click the card to include the
 *   technique. Category color borders on selected state tie visual identity to the
 *   analytical meaning (green=diagnostic, amber=contrarian, purple=imaginative).
 */
import type { TechniqueInfo } from '../../api/types'

interface TechniqueSelectorProps {
  techniques: TechniqueInfo[]
  selected: string[]
  onChange: (selected: string[]) => void
  disabled?: boolean
}

const CATEGORY_LABELS: Record<string, string> = {
  diagnostic: 'Diagnostic',
  contrarian: 'Contrarian',
  imaginative: 'Imaginative',
}

const CATEGORY_DESC: Record<string, string> = {
  diagnostic: 'Structured evaluation of evidence and hypotheses',
  contrarian: 'Challenge assumptions, surface alternative views',
  imaginative: 'Scenario projection and creative analysis',
}

type Category = 'diagnostic' | 'contrarian' | 'imaginative'
const CATEGORIES: Category[] = ['diagnostic', 'contrarian', 'imaginative']

function toggle(arr: string[], id: string): string[] {
  return arr.includes(id) ? arr.filter(x => x !== id) : [...arr, id]
}

export default function TechniqueSelector({ techniques, selected, onChange, disabled = false }: TechniqueSelectorProps) {
  const byCategory = CATEGORIES.reduce<Record<Category, TechniqueInfo[]>>(
    (acc, cat) => {
      acc[cat] = techniques.filter(t => t.category === cat).sort((a, b) => a.order - b.order)
      return acc
    },
    { diagnostic: [], contrarian: [], imaginative: [] }
  )

  return (
    <div className="technique-selector">
      <div className="technique-selector-header">
        <span className="technique-selector-label">Analytical Techniques</span>
        <span className="technique-selector-hint">
          {selected.length === 0
            ? 'Auto-select — all applicable techniques will run'
            : `${selected.length} technique${selected.length !== 1 ? 's' : ''} selected`}
        </span>
      </div>

      {selected.length > 0 && (
        <button
          className="technique-selector-reset"
          onClick={() => onChange([])}
          disabled={disabled}
          type="button"
        >
          Reset to auto-select
        </button>
      )}

      <div className="technique-columns">
        {CATEGORIES.map(cat => (
          <div key={cat} className={`technique-column technique-column-${cat}`}>
            <div className="technique-column-header">
              <span className={`technique-column-title technique-column-title-${cat}`}>
                {CATEGORY_LABELS[cat]}
              </span>
              <span className="technique-column-desc">{CATEGORY_DESC[cat]}</span>
            </div>
            <div className="technique-column-cards">
              {byCategory[cat].map(t => {
                const isSelected = selected.includes(t.id)
                return (
                  <button
                    key={t.id}
                    type="button"
                    className={`technique-card technique-card-${cat} ${isSelected ? `technique-card-selected technique-card-selected-${cat}` : ''}`}
                    onClick={() => !disabled && onChange(toggle(selected, t.id))}
                    disabled={disabled}
                  >
                    <span className="technique-card-name">{t.name}</span>
                    <span className="technique-card-desc">{t.description}</span>
                    {isSelected && (
                      <span className={`technique-card-check technique-card-check-${cat}`}>✓</span>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/**
 * @decision DEC-DESKTOP-PROVIDER-CONFIG-001
 * @title ProviderConfig: radio-button provider selection with model override
 * @status accepted
 * @rationale Provider selection is binary — you pick one and run with it.
 *   Radio buttons are the correct control. Disabled providers show a "No API Key"
 *   badge so analysts understand the constraint immediately rather than getting
 *   a cryptic API error at run time. The model override is optional text input
 *   because model names are not a bounded enum — providers release new models
 *   frequently and the field should accept arbitrary strings.
 */
import type { ProviderInfo } from '../../api/types'

interface ProviderConfigProps {
  providers: ProviderInfo[]
  selected: string
  onSelect: (name: string) => void
  model: string
  onModelChange: (model: string) => void
  disabled?: boolean
}

export default function ProviderConfig({
  providers,
  selected,
  onSelect,
  model,
  onModelChange,
  disabled = false,
}: ProviderConfigProps) {
  const selectedProvider = providers.find(p => p.name === selected)

  return (
    <div className="provider-config">
      <span className="provider-config-label">LLM Provider</span>
      <div className="provider-radio-group">
        {providers.map(p => (
          <label
            key={p.name}
            className={`provider-radio-item ${!p.has_api_key ? 'provider-radio-disabled' : ''} ${selected === p.name ? 'provider-radio-selected' : ''}`}
          >
            <input
              type="radio"
              name="provider"
              value={p.name}
              checked={selected === p.name}
              onChange={() => !disabled && p.has_api_key && onSelect(p.name)}
              disabled={disabled || !p.has_api_key}
              className="provider-radio-input"
            />
            <span className="provider-radio-name">{p.name}</span>
            {p.has_api_key ? (
              <span className="provider-radio-model">{p.default_model}</span>
            ) : (
              <span className="intel-badge badge-red">No API Key</span>
            )}
          </label>
        ))}
      </div>

      {selectedProvider && (
        <div className="model-override">
          <label className="model-override-label">
            Model Override
            <span className="model-override-hint"> (optional — leave blank for default)</span>
          </label>
          <input
            type="text"
            className="model-override-input"
            placeholder={selectedProvider.default_model}
            value={model}
            onChange={e => onModelChange(e.target.value)}
            disabled={disabled}
          />
        </div>
      )}
    </div>
  )
}

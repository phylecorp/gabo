/**
 * @decision DEC-DESKTOP-SETTINGS-PAGE-001
 * @title Settings page: per-provider cards with masked key display, test, and save
 * @status accepted
 * @rationale Each provider gets its own card so the user can configure them
 *   independently. Keys are shown masked (preview only) with a reveal toggle for
 *   the edit flow. "Test Connection" calls the backend's test-provider endpoint
 *   so the user gets immediate feedback without saving first. Save is global —
 *   one PUT covers all providers to keep the backend interaction simple.
 *   Status indicators mirror the dashboard provider strip for visual consistency.
 *
 * @decision DEC-DESKTOP-SETTINGS-PAGE-002
 * @title Model dropdowns replace free-text inputs, with graceful text fallback
 * @status accepted
 * @rationale Dropdowns populated from GET /api/config/models/{provider} prevent
 *   typos and surface all available models. When the fetch fails (no key, network
 *   error) the component falls back to the original free-text <input> so users
 *   can still type a custom model ID. Research model dropdowns are shown only for
 *   providers with non-empty research model lists (Perplexity, OpenAI, Gemini).
 *   Anthropic has no research provider so its research list is always empty.
 *   Brave has no model concept at all and is hidden via HIDE_MODEL_PROVIDERS.
 */
import { useState, type ChangeEvent } from 'react'
import { useSettings, useUpdateSettings, useTestProvider } from '../hooks/useSettings'
import { useModels } from '../hooks/useModels'
import type { ProviderSettingsResponse, TestProviderResponse, ModelInfo } from '../api/types'
import ErrorState from '../components/common/ErrorState'

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: 'Anthropic',
  openai: 'OpenAI',
  gemini: 'Google Gemini',
  perplexity: 'Perplexity',
  brave: 'Brave Search',
}

const PROVIDER_MODEL_PLACEHOLDERS: Record<string, string> = {
  anthropic: 'claude-opus-4-6',
  openai: 'o3',
  gemini: 'gemini-2.5-pro',
  perplexity: 'sonar-deep-research',
  brave: '',
}

/**
 * Research providers use a different API (no LLM model selection).
 * Brave has no model concept at all; Perplexity always uses sonar-deep-research
 * but we still expose the model field so advanced users can override if needed.
 * Only Brave hides the model field entirely.
 */
const HIDE_MODEL_PROVIDERS = new Set(['brave'])

interface ProviderDraft {
  api_key: string
  default_model: string
  research_model: string
  editing_key: boolean  // true while the user is actively entering a new key
  show_key: boolean     // show the raw input value while typing
}

function makeInitialDraft(): ProviderDraft {
  return { api_key: '', default_model: '', research_model: '', editing_key: false, show_key: false }
}

interface TestState {
  loading: boolean
  result: TestProviderResponse | null
}

export default function Settings() {
  const { data: settings, isLoading, error: settingsError, refetch } = useSettings()
  const updateMutation = useUpdateSettings()
  const testMutation = useTestProvider()

  // Local draft state for each provider's key + model
  const [drafts, setDrafts] = useState<Record<string, ProviderDraft>>({})
  const [testStates, setTestStates] = useState<Record<string, TestState>>({})
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [saveError, setSaveError] = useState<string | null>(null)

  const providers = settings?.providers ?? {}

  function getDraft(name: string): ProviderDraft {
    const stored = drafts[name]
    if (stored) return stored
    // Initialize from server info if available
    const serverInfo = providers[name]
    if (serverInfo) {
      return {
        api_key: '',
        default_model: serverInfo.default_model ?? '',
        research_model: serverInfo.research_model ?? '',
        editing_key: false,
        show_key: false,
      }
    }
    return makeInitialDraft()
  }

  function setDraft(name: string, patch: Partial<ProviderDraft>) {
    setDrafts(prev => ({
      ...prev,
      [name]: { ...getDraft(name), ...patch },
    }))
  }

  function handleStartEditKey(name: string) {
    setDraft(name, { editing_key: true, api_key: '', show_key: false })
  }

  function handleCancelEditKey(name: string) {
    setDraft(name, { editing_key: false, api_key: '', show_key: false })
  }

  function handleKeyChange(name: string, value: string) {
    setDraft(name, { api_key: value })
  }

  function handleModelChange(name: string, value: string) {
    setDraft(name, { default_model: value })
  }

  function handleResearchModelChange(name: string, value: string) {
    setDraft(name, { research_model: value })
  }

  function handleRemoveKey(name: string) {
    setDraft(name, { editing_key: true, api_key: '', show_key: false })
  }

  async function handleTestProvider(name: string) {
    const draft = getDraft(name)
    const serverInfo: ProviderSettingsResponse | undefined = providers[name]
    // Use draft key if editing, otherwise we can't test (no key to test with)
    const keyToTest = draft.api_key || ''
    if (!keyToTest) return

    setTestStates(prev => ({
      ...prev,
      [name]: { loading: true, result: null },
    }))

    try {
      const result = await testMutation.mutateAsync({
        provider: name,
        api_key: keyToTest,
        model: draft.default_model || serverInfo?.default_model || undefined,
      })
      setTestStates(prev => ({
        ...prev,
        [name]: { loading: false, result },
      }))
    } catch (err) {
      setTestStates(prev => ({
        ...prev,
        [name]: {
          loading: false,
          result: { success: false, error: String(err), model_used: '' },
        },
      }))
    }
  }

  async function handleSave() {
    setSaveStatus('saving')
    setSaveError(null)

    // Build the payload: include every provider in drafts
    const providerPayload: Record<string, { api_key: string; default_model: string; research_model?: string }> = {}

    for (const name of Object.keys(providers)) {
      const draft = getDraft(name)
      const serverInfo: ProviderSettingsResponse | undefined = providers[name]

      // If editing key, use draft value (may be empty = remove key)
      // If not editing, preserve existing key by sending empty string
      // (backend will preserve existing config file entry)
      const apiKey = draft.editing_key ? draft.api_key : ''
      const model = draft.default_model || serverInfo?.default_model || ''
      const researchModel = draft.research_model || serverInfo?.research_model || ''

      providerPayload[name] = {
        api_key: apiKey,
        default_model: model,
        research_model: researchModel,
      }
    }

    try {
      await updateMutation.mutateAsync({ providers: providerPayload })
      setSaveStatus('saved')
      // Reset all editing states after successful save
      setDrafts({})
      setTimeout(() => setSaveStatus('idle'), 2500)
    } catch (err) {
      setSaveStatus('error')
      setSaveError(err instanceof Error ? err.message : String(err))
    }
  }

  if (isLoading) {
    return (
      <div className="settings-page">
        <div className="settings-loading">
          <span className="text-secondary text-sm">Loading settings...</span>
        </div>
      </div>
    )
  }

  if (settingsError) {
    return (
      <div className="settings-page">
        <ErrorState
          message={`Failed to load settings: ${(settingsError as Error).message}`}
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  return (
    <div className="settings-page">
      <div className="settings-header">
        <h2 className="settings-title">Settings</h2>
        <span className="settings-subtitle text-muted text-xs">
          Configure LLM and research provider API keys
        </span>
      </div>

      <div className="settings-providers">
        {Object.entries(providers).map(([name, info]) => (
          <ProviderCard
            key={name}
            name={name}
            label={PROVIDER_LABELS[name] ?? name}
            modelPlaceholder={PROVIDER_MODEL_PLACEHOLDERS[name] ?? ''}
            hideModel={HIDE_MODEL_PROVIDERS.has(name)}
            info={info}
            draft={getDraft(name)}
            testState={testStates[name] ?? { loading: false, result: null }}
            onStartEditKey={() => handleStartEditKey(name)}
            onCancelEditKey={() => handleCancelEditKey(name)}
            onKeyChange={(v) => handleKeyChange(name, v)}
            onModelChange={(v) => handleModelChange(name, v)}
            onResearchModelChange={(v) => handleResearchModelChange(name, v)}
            onRemoveKey={() => handleRemoveKey(name)}
            onTestProvider={() => handleTestProvider(name)}
            onToggleShowKey={() => setDraft(name, { show_key: !getDraft(name).show_key })}
          />
        ))}
      </div>

      <div className="settings-footer">
        {saveStatus === 'error' && saveError && (
          <span className="settings-save-error text-sm">
            {saveError}
          </span>
        )}
        {saveStatus === 'saved' && (
          <span className="settings-save-ok text-sm">
            Settings saved
          </span>
        )}
        <button
          className="btn-primary"
          onClick={handleSave}
          disabled={saveStatus === 'saving'}
        >
          {saveStatus === 'saving' ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ProviderCard
// ---------------------------------------------------------------------------

interface ProviderCardProps {
  name: string
  label: string
  modelPlaceholder: string
  /** When true, the Default Model section is hidden (e.g. Brave Search has no model). */
  hideModel?: boolean
  info: ProviderSettingsResponse
  draft: ProviderDraft
  testState: TestState
  onStartEditKey: () => void
  onCancelEditKey: () => void
  onKeyChange: (value: string) => void
  onModelChange: (value: string) => void
  onResearchModelChange: (value: string) => void
  onRemoveKey: () => void
  onTestProvider: () => void
  onToggleShowKey: () => void
}

function ProviderCard({
  name,
  label,
  modelPlaceholder,
  hideModel = false,
  info,
  draft,
  testState,
  onStartEditKey,
  onCancelEditKey,
  onKeyChange,
  onModelChange,
  onResearchModelChange,
  onRemoveKey,
  onTestProvider,
  onToggleShowKey,
}: ProviderCardProps) {
  const isConnected = info.has_api_key
  const isEditingKey = draft.editing_key

  // Fetch models for this provider. Always fetch when provider has a key or
  // is being configured, so dropdowns are ready when the user opens the card.
  const { models, isLoading: modelsLoading, error: modelsError } = useModels(
    name,
    !HIDE_MODEL_PROVIDERS.has(name), // skip brave — no model concept
  )

  const hasAnalysisModels = models.analysis.length > 0
  const hasResearchModels = models.research.length > 0

  // Use dropdown when model list is available; fall back to text input on error
  // or when list is still loading and we have no cached data.
  const useAnalysisDropdown = hasAnalysisModels && !modelsError
  const useResearchDropdown = hasResearchModels && !modelsError

  return (
    <div className="settings-provider-card">
      {/* Card header */}
      <div className="settings-provider-header">
        <div className="settings-provider-name-row">
          <span className="settings-provider-name">{label}</span>
          <span className={`intel-badge ${isConnected ? 'badge-green' : 'badge-red'}`}>
            {isConnected ? 'Connected' : 'Not configured'}
          </span>
        </div>
        <div className="settings-provider-dot-row">
          <span className={`status-dot ${isConnected ? 'status-dot-ok' : 'status-dot-error'}`} />
        </div>
      </div>

      {/* API Key section */}
      <div className="form-section form-section-spaced">
        <label className="form-label" htmlFor={`key-${name}`}>API Key</label>

        {!isEditingKey && info.has_api_key && (
          <div className="settings-key-row">
            <span className="settings-key-preview font-mono text-xs text-secondary">
              {info.api_key_preview}
            </span>
            <div className="settings-key-actions">
              <button className="btn-secondary settings-btn-sm" onClick={onStartEditKey}>
                Change
              </button>
              <button
                className="btn-secondary settings-btn-sm settings-btn-danger"
                onClick={onRemoveKey}
              >
                Remove
              </button>
            </div>
          </div>
        )}

        {!isEditingKey && !info.has_api_key && (
          <button className="btn-secondary settings-btn-sm" onClick={onStartEditKey}>
            Add API Key
          </button>
        )}

        {isEditingKey && (
          <div className="settings-key-edit">
            <div className="settings-key-input-row">
              <input
                id={`key-${name}`}
                type={draft.show_key ? 'text' : 'password'}
                className="model-override-input settings-key-input"
                value={draft.api_key}
                onChange={(e: ChangeEvent<HTMLInputElement>) => onKeyChange(e.target.value)}
                placeholder={`Enter ${label} API key`}
                autoComplete="off"
                spellCheck={false}
              />
              <button
                className="btn-secondary settings-btn-sm"
                onClick={onToggleShowKey}
                type="button"
                title={draft.show_key ? 'Hide key' : 'Show key'}
              >
                {draft.show_key ? 'Hide' : 'Show'}
              </button>
            </div>
            <div className="settings-key-edit-actions">
              {draft.api_key && (
                <button
                  className="btn-secondary settings-btn-sm"
                  onClick={onTestProvider}
                  disabled={testState.loading}
                >
                  {testState.loading ? 'Testing...' : 'Test Connection'}
                </button>
              )}
              <button className="btn-secondary settings-btn-sm" onClick={onCancelEditKey}>
                Cancel
              </button>
            </div>
            {testState.result && (
              <div
                className={`settings-test-result text-xs ${testState.result.success ? 'settings-test-ok' : 'settings-test-fail'}`}
              >
                {testState.result.success
                  ? `Connected — model: ${testState.result.model_used}`
                  : `Failed: ${testState.result.error}`}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Analysis model section — hidden for providers without a model concept (e.g. Brave Search) */}
      {!hideModel && (
        <div className="form-section form-section-spaced">
          <label className="form-label" htmlFor={`model-${name}`}>
            {hasResearchModels ? 'Analysis Model' : 'Default Model'}
          </label>
          {useAnalysisDropdown ? (
            <ModelSelect
              id={`model-${name}`}
              models={models.analysis}
              value={draft.default_model}
              placeholder={info.default_model || modelPlaceholder}
              onChange={onModelChange}
              loading={modelsLoading && !hasAnalysisModels}
            />
          ) : (
            <input
              id={`model-${name}`}
              type="text"
              className="model-override-input"
              value={draft.default_model}
              onChange={(e: ChangeEvent<HTMLInputElement>) => onModelChange(e.target.value)}
              placeholder={info.default_model || modelPlaceholder}
            />
          )}
          {!useAnalysisDropdown && (
            <span className="form-label-hint text-xs">
              Leave blank to use the built-in default ({modelPlaceholder})
            </span>
          )}
        </div>
      )}

      {/* Research model section — shown only for providers with research models */}
      {!hideModel && useResearchDropdown && (
        <div className="form-section form-section-spaced">
          <label className="form-label" htmlFor={`research-model-${name}`}>
            Research Model
          </label>
          <ModelSelect
            id={`research-model-${name}`}
            models={models.research}
            value={draft.research_model}
            placeholder={info.research_model || ''}
            onChange={onResearchModelChange}
            loading={modelsLoading && !hasResearchModels}
          />
        </div>
      )}

      {/* Source badge */}
      {info.source !== 'default' && (
        <div className="settings-source-badge-row">
          <span className="intel-badge badge-cyan settings-source-badge">
            {info.source === 'config_file' ? 'from config file' : 'from environment'}
          </span>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// ModelSelect
// ---------------------------------------------------------------------------

interface ModelSelectProps {
  id: string
  models: ModelInfo[]
  value: string
  placeholder: string
  onChange: (value: string) => void
  loading?: boolean
}

/**
 * Dropdown select for choosing a model from a list fetched from the backend.
 *
 * When value is empty, the first option shown is a prompt to "select a model"
 * or "(default: <id>)" to make it clear what happens when the field is left
 * blank. This mirrors the text input placeholder behavior.
 */
function ModelSelect({ id, models, value, placeholder, onChange, loading }: ModelSelectProps) {
  if (loading) {
    return (
      <select id={id} className="model-override-input" disabled>
        <option>Loading models...</option>
      </select>
    )
  }

  // Find the default model to show in the empty-selection prompt
  const defaultModel = models.find(m => m.default)
  const emptyLabel = placeholder
    ? `(default: ${placeholder})`
    : defaultModel
      ? `(default: ${defaultModel.id})`
      : 'Select a model'

  return (
    <select
      id={id}
      className="model-override-input"
      value={value}
      onChange={(e: ChangeEvent<HTMLSelectElement>) => onChange(e.target.value)}
    >
      <option value="">{emptyLabel}</option>
      {models.map(m => (
        <option key={m.id} value={m.id}>
          {m.name}{m.default ? ' (default)' : ''}
        </option>
      ))}
    </select>
  )
}

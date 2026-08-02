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
 *
 * @decision DEC-MODELS-004
 * @title Settings dropdowns populated from models endpoint with free-text fallback
 * @status accepted
 * @rationale Dropdowns for usability (eliminates typos, surfaces real options);
 *   free-text fallback for resilience (Settings still works when models endpoint
 *   is unreachable — no API key yet, network issue). The useModels(provider) hook
 *   encapsulates the fetch + error state; ProviderCard switches between
 *   ModelSelect and <input> based on whether a non-empty model list arrived.
 *   Addresses REQ-P0-002 (model selection) and REQ-P1-002 (graceful degradation).
 */
import { useState, useRef, useEffect, type ChangeEvent } from 'react'
import { useSettings, useUpdateSettings, useTestProvider } from '../hooks/useSettings'
import { useModels } from '../hooks/useModels'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { ProviderSettingsResponse, TestProviderResponse, ModelInfo, TemplateInfo, StyleTextResponse, TechniqueInfo, TechniqueOverride, AdversarialSettings } from '../api/types'
import ErrorState from '../components/common/ErrorState'
import { useApiContext } from '../api/context'

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: 'Anthropic',
  openai: 'OpenAI',
  gemini: 'Google Gemini',
  perplexity: 'Perplexity',
  brave: 'Brave Search',
  ollama: 'Ollama',
  lmstudio: 'LM Studio',
}

const PROVIDER_MODEL_PLACEHOLDERS: Record<string, string> = {
  anthropic: 'claude-opus-4-6',
  openai: 'o3',
  gemini: 'gemini-2.5-pro',
  perplexity: 'sonar-deep-research',
  brave: '',
  ollama: 'llama3.2',
  lmstudio: 'model-key-from-lm-studio',
}

/**
 * Research providers use a different API (no LLM model selection).
 * Brave has no model concept at all; Perplexity always uses sonar-deep-research
 * but we still expose the model field so advanced users can override if needed.
 * Only Brave hides the model field entirely.
 */
const HIDE_MODEL_PROVIDERS = new Set(['brave'])

/** Local native-API providers — no cloud API key required. */
const LOCAL_PROVIDERS = new Set(['ollama', 'lmstudio'])

/** Ollama ignores auth; hide the API key field entirely. */
const HIDE_API_KEY_PROVIDERS = new Set(['ollama'])

const DEFAULT_BASE_URLS: Record<string, string> = {
  ollama: 'http://127.0.0.1:11434',
  lmstudio: 'http://127.0.0.1:1234',
}

interface ProviderDraft {
  api_key: string
  default_model: string
  research_model: string
  base_url: string
  editing_key: boolean  // true while the user is actively entering a new key
  show_key: boolean     // show the raw input value while typing
}

function makeInitialDraft(): ProviderDraft {
  return {
    api_key: '',
    default_model: '',
    research_model: '',
    base_url: '',
    editing_key: false,
    show_key: false,
  }
}

interface TestState {
  loading: boolean
  result: TestProviderResponse | null
}

export default function Settings() {
  const { data: settings, isLoading, error: settingsError, refetch } = useSettings()
  const updateMutation = useUpdateSettings()
  const testMutation = useTestProvider()
  const queryClient = useQueryClient()

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
        base_url: serverInfo.base_url ?? DEFAULT_BASE_URLS[name] ?? '',
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

  function handleBaseUrlChange(name: string, value: string) {
    setDraft(name, { base_url: value })
  }

  function handleRemoveKey(name: string) {
    setDraft(name, { editing_key: true, api_key: '', show_key: false })
  }

  async function handleTestProvider(name: string) {
    const draft = getDraft(name)
    const serverInfo: ProviderSettingsResponse | undefined = providers[name]
    const isLocal = LOCAL_PROVIDERS.has(name)
    // Local providers can be tested without a key; cloud providers need one.
    const keyToTest = draft.api_key || ''
    if (!isLocal && !keyToTest) return

    setTestStates(prev => ({
      ...prev,
      [name]: { loading: true, result: null },
    }))

    try {
      const result = await testMutation.mutateAsync({
        provider: name,
        api_key: keyToTest,
        model: draft.default_model || serverInfo?.default_model || undefined,
        base_url: isLocal
          ? (draft.base_url || serverInfo?.base_url || DEFAULT_BASE_URLS[name])
          : undefined,
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
    const providerPayload: Record<string, {
      api_key: string
      default_model: string
      research_model?: string
      base_url?: string
    }> = {}

    for (const name of Object.keys(providers)) {
      const draft = getDraft(name)
      const serverInfo: ProviderSettingsResponse | undefined = providers[name]

      // If editing key, use draft value (may be empty = remove key)
      // If not editing, preserve existing key by sending empty string
      // (backend will preserve existing config file entry)
      const apiKey = draft.editing_key ? draft.api_key : ''
      const model = draft.default_model || serverInfo?.default_model || ''
      const researchModel = draft.research_model || serverInfo?.research_model || ''
      const baseUrl = LOCAL_PROVIDERS.has(name)
        ? (draft.base_url || serverInfo?.base_url || DEFAULT_BASE_URLS[name] || '')
        : ''

      providerPayload[name] = {
        api_key: apiKey,
        default_model: model,
        research_model: researchModel,
        ...(baseUrl ? { base_url: baseUrl } : {}),
      }
    }

    try {
      await updateMutation.mutateAsync({ providers: providerPayload })
      setSaveStatus('saved')
      // Reset all editing states after successful save
      setDrafts({})
      // Invalidate all cached model queries so dropdowns refetch from the
      // backend — which re-fetches from the provider API now that keys have
      // changed. Without this the 5-minute staleTime would keep the
      // pre-key fallback lists alive.
      queryClient.invalidateQueries({ queryKey: ['models'] })
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
            hideApiKey={HIDE_API_KEY_PROVIDERS.has(name)}
            isLocal={LOCAL_PROVIDERS.has(name)}
            info={info}
            draft={getDraft(name)}
            testState={testStates[name] ?? { loading: false, result: null }}
            onStartEditKey={() => handleStartEditKey(name)}
            onCancelEditKey={() => handleCancelEditKey(name)}
            onKeyChange={(v) => handleKeyChange(name, v)}
            onModelChange={(v) => handleModelChange(name, v)}
            onResearchModelChange={(v) => handleResearchModelChange(name, v)}
            onBaseUrlChange={(v) => handleBaseUrlChange(name, v)}
            onRemoveKey={() => handleRemoveKey(name)}
            onTestProvider={() => handleTestProvider(name)}
            onToggleShowKey={() => setDraft(name, { show_key: !getDraft(name).show_key })}
          />
        ))}
      </div>

      <TechniqueOverridesCard />

      <AdversarialSettingsCard />

      <WritingStyleCard />

      <ReportTemplatesCard />

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
// WritingStyleCard
// ---------------------------------------------------------------------------

/**
 * Settings card for configuring user-provided style guide and writing exemplar.
 *
 * The style guide defines writing rules (tone, vocabulary, banned phrases) that
 * override or supplement the built-in Sherman Kent defaults. The exemplar provides
 * a concrete voice sample the model can match. Both are persisted to ~/.sat/ via
 * the backend PUT endpoints and injected into report/synthesis system prompts on
 * every analysis run.
 *
 * Local textarea state is initialized once from server data (via the initialized
 * flag) so edits are not clobbered by React Query refetches while the user types.
 */
function WritingStyleCard() {
  const { client } = useApiContext()
  const queryClient = useQueryClient()
  const [styleGuide, setStyleGuide] = useState('')
  const [exemplar, setExemplar] = useState('')
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [saveError, setSaveError] = useState<string | null>(null)

  const { data: styleData } = useQuery({
    queryKey: ['style-guide'],
    queryFn: () => client!.getStyleGuide(),
    enabled: !!client,
    staleTime: 0,
  })

  const { data: exemplarData } = useQuery({
    queryKey: ['exemplar'],
    queryFn: () => client!.getExemplar(),
    enabled: !!client,
    staleTime: 0,
  })

  // Sync server data into local state on load — only once, so in-flight edits
  // are not overwritten by React Query background refetches.
  const [initialized, setInitialized] = useState(false)
  useEffect(() => {
    if (!initialized && styleData && exemplarData) {
      setStyleGuide(styleData.content || '')
      setExemplar(exemplarData.content || '')
      setInitialized(true)
    }
  }, [initialized, styleData, exemplarData])

  const hasContent = styleGuide.trim().length > 0 || exemplar.trim().length > 0
  const serverHasContent =
    (styleData?.content || '').trim().length > 0 ||
    (exemplarData?.content || '').trim().length > 0

  async function handleSave() {
    if (!client) return
    setSaveStatus('saving')
    setSaveError(null)
    try {
      await Promise.all([
        client.updateStyleGuide(styleGuide),
        client.updateExemplar(exemplar),
      ])
      setSaveStatus('saved')
      queryClient.invalidateQueries({ queryKey: ['style-guide'] })
      queryClient.invalidateQueries({ queryKey: ['exemplar'] })
      setTimeout(() => setSaveStatus('idle'), 2500)
    } catch (err) {
      setSaveStatus('error')
      setSaveError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleClear() {
    if (!client) return
    setSaveStatus('saving')
    setSaveError(null)
    try {
      await Promise.all([
        client.updateStyleGuide(''),
        client.updateExemplar(''),
      ])
      setStyleGuide('')
      setExemplar('')
      setSaveStatus('saved')
      queryClient.invalidateQueries({ queryKey: ['style-guide'] })
      queryClient.invalidateQueries({ queryKey: ['exemplar'] })
      setTimeout(() => setSaveStatus('idle'), 2500)
    } catch (err) {
      setSaveStatus('error')
      setSaveError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="settings-provider-card">
      <div className="settings-provider-header">
        <div className="settings-provider-name-row">
          <span className="settings-provider-name">Writing Style</span>
          <span className={`intel-badge ${serverHasContent ? 'badge-cyan' : 'badge-green'}`}>
            {serverHasContent ? 'Custom' : 'Default'}
          </span>
        </div>
      </div>

      <div className="form-section form-section-spaced">
        <label className="form-label">Style Guide</label>
        <span className="form-label-hint text-xs">
          Define your writing rules: tone, vocabulary, sentence structure, what to avoid.
          Overrides the built-in defaults where they conflict.
        </span>
        <textarea
          className="model-override-input"
          style={{ minHeight: '120px', resize: 'vertical', fontFamily: 'inherit' }}
          value={styleGuide}
          onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setStyleGuide(e.target.value)}
          placeholder="e.g., Use short declarative sentences. Prefer Anglo-Saxon vocabulary over Latinate. Never use 'it is worth noting.'"
        />
      </div>

      <div className="form-section form-section-spaced">
        <label className="form-label">Writing Exemplar</label>
        <span className="form-label-hint text-xs">
          Paste 1-3 paragraphs of writing whose voice you want reports to match.
          The model will study its tone, rhythm, and vocabulary.
        </span>
        <textarea
          className="model-override-input"
          style={{ minHeight: '150px', resize: 'vertical', fontFamily: 'inherit' }}
          value={exemplar}
          onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setExemplar(e.target.value)}
          placeholder="Paste an example of the writing style you want..."
        />
      </div>

      <div className="settings-key-edit-actions" style={{ marginTop: '0.5rem' }}>
        <button
          className="btn-primary settings-btn-sm"
          onClick={handleSave}
          disabled={saveStatus === 'saving'}
        >
          {saveStatus === 'saving' ? 'Saving...' : 'Save Style'}
        </button>
        {hasContent && (
          <button
            className="btn-secondary settings-btn-sm settings-btn-danger"
            onClick={handleClear}
            disabled={saveStatus === 'saving'}
          >
            Clear
          </button>
        )}
        {saveStatus === 'saved' && (
          <span className="settings-test-result settings-test-ok text-xs">Saved</span>
        )}
        {saveStatus === 'error' && saveError && (
          <span className="settings-test-result settings-test-fail text-xs">{saveError}</span>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// TechniqueOverridesCard
// ---------------------------------------------------------------------------

/**
 * Settings card for per-technique model and temperature overrides.
 *
 * Allows users to override the model or temperature for individual CIA
 * tradecraft techniques. Techniques are grouped by category (diagnostic,
 * contrarian, imaginative) in collapsible sections — categories start
 * collapsed because this is an advanced feature most users won't need.
 *
 * The active provider is the first one that has has_api_key: true in settings.
 * Its model list populates the model dropdown. If no provider has a key,
 * falls back to text input. Temperature inputs use the technique's
 * default_temperature as placeholder so users understand what they're overriding.
 *
 * Save is independent of the provider Save Settings button — this card
 * manages its own PUT /api/config/settings lifecycle, sending only the
 * technique_overrides dict (providers are left unchanged by sending the
 * existing provider state).
 *
 * @decision DEC-TECHNIQUE-OVERRIDES-UI-001
 * @title TechniqueOverridesCard: independent save lifecycle, category-collapsible rows
 * @status accepted
 * @rationale Technique overrides are advanced settings that most users won't touch.
 *   Collapsible categories reduce visual noise while keeping the feature discoverable.
 *   The card has its own Save button (not coupled to the provider Save Settings button)
 *   so technique override changes can be saved independently of provider key changes —
 *   consistent with WritingStyleCard's pattern. Draft state tracks the full
 *   technique_overrides dict, initialized from server data once, then managed locally.
 */
function TechniqueOverridesCard() {
  const { client } = useApiContext()
  const queryClient = useQueryClient()
  const { data: settings } = useSettings()

  // Fetch all registered techniques for category grouping and default_temperature placeholders.
  const { data: techniques = [] } = useQuery<TechniqueInfo[]>({
    queryKey: ['techniques'],
    queryFn: () => client!.getTechniques(),
    enabled: !!client,
    staleTime: 5 * 60 * 1000,
  })

  // Determine the active analysis provider (first with a key configured).
  // We use this provider's model list for the technique model dropdowns.
  const providers = settings?.providers ?? {}
  const activeProviderName = Object.entries(providers).find(
    ([name, info]) => info.has_api_key && !HIDE_MODEL_PROVIDERS.has(name)
  )?.[0] ?? null

  // Fetch models for the active provider. If no provider has a key, models will be empty.
  const { models: activeModels } = useModels(activeProviderName ?? '', !!activeProviderName)
  const analysisModels = activeModels.analysis

  // Draft state: technique_id → TechniqueOverride.
  // Initialized from server on first load; tracks local edits until Save.
  const [overrideDraft, setOverrideDraft] = useState<Record<string, TechniqueOverride>>({})
  const [initialized, setInitialized] = useState(false)

  useEffect(() => {
    if (!initialized && settings) {
      setOverrideDraft(settings.technique_overrides ?? {})
      setInitialized(true)
    }
  }, [initialized, settings])

  // Category collapse state. Default: all collapsed (advanced feature).
  const [openCategories, setOpenCategories] = useState<Set<string>>(new Set())

  function toggleCategory(cat: string) {
    setOpenCategories(prev => {
      const next = new Set(prev)
      if (next.has(cat)) next.delete(cat)
      else next.add(cat)
      return next
    })
  }

  // Save state
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [saveError, setSaveError] = useState<string | null>(null)

  function setOverride(techniqueId: string, patch: Partial<TechniqueOverride>) {
    setOverrideDraft(prev => {
      const current = prev[techniqueId] ?? {}
      const updated = { ...current, ...patch }
      return { ...prev, [techniqueId]: updated }
    })
  }

  // Count active overrides (entries where model or temperature is set).
  const activeCount = Object.values(overrideDraft).filter(
    ov => (ov.model ?? '') !== '' || ov.temperature != null
  ).length

  async function handleSave() {
    if (!client) return
    setSaveStatus('saving')
    setSaveError(null)
    try {
      // Strip entries where both model and temperature are empty/null.
      // The backend also cleans these but we do it client-side too for consistency.
      const cleaned: Record<string, TechniqueOverride> = {}
      for (const [tid, ov] of Object.entries(overrideDraft)) {
        const model = ov.model ?? null
        const temperature = ov.temperature ?? null
        if (model !== null && model !== '' || temperature !== null) {
          cleaned[tid] = {
            model: (model === '') ? null : model,
            temperature,
          }
        }
      }

      // Build the full settings payload. Providers are passed as-is (no API keys
      // in the payload — empty string signals "keep existing" on the backend).
      const providerPayload: Record<string, { api_key: string; default_model: string; research_model: string }> = {}
      for (const [name, info] of Object.entries(providers)) {
        providerPayload[name] = {
          api_key: '',
          default_model: info.default_model,
          research_model: info.research_model,
        }
      }

      await client.updateSettings({
        providers: providerPayload,
        technique_overrides: cleaned,
      })
      setSaveStatus('saved')
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      setTimeout(() => setSaveStatus('idle'), 2500)
    } catch (err) {
      setSaveStatus('error')
      setSaveError(err instanceof Error ? err.message : String(err))
    }
  }

  function handleClearAll() {
    setOverrideDraft({})
  }

  // Group techniques by category.
  const CATEGORY_ORDER = ['diagnostic', 'contrarian', 'imaginative'] as const
  const byCategory = new Map<string, TechniqueInfo[]>()
  for (const tech of techniques) {
    const list = byCategory.get(tech.category) ?? []
    list.push(tech)
    byCategory.set(tech.category, list)
  }
  // Sort each category's techniques by their order field.
  for (const [cat, list] of byCategory) {
    byCategory.set(cat, [...list].sort((a, b) => a.order - b.order))
  }

  const CATEGORY_LABELS: Record<string, string> = {
    diagnostic: 'Diagnostic',
    contrarian: 'Contrarian',
    imaginative: 'Imaginative',
  }

  return (
    <div className="settings-provider-card">
      <div className="settings-provider-header">
        <div className="settings-provider-name-row">
          <span className="settings-provider-name">Technique Overrides</span>
          <span className={`intel-badge ${activeCount > 0 ? 'badge-cyan' : 'badge-green'}`}>
            {activeCount > 0 ? `${activeCount} override${activeCount > 1 ? 's' : ''}` : 'Default'}
          </span>
        </div>
      </div>

      <div className="form-section">
        <span className="form-label-hint text-xs">
          Override model or temperature for individual techniques. Leave blank to use defaults.
        </span>
      </div>

      {CATEGORY_ORDER.map(cat => {
        const catTechniques = byCategory.get(cat) ?? []
        if (catTechniques.length === 0) return null
        const isOpen = openCategories.has(cat)
        return (
          <div key={cat} className="form-section form-section-spaced">
            <button
              type="button"
              className="btn-secondary settings-btn-sm"
              style={{ width: '100%', textAlign: 'left', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
              onClick={() => toggleCategory(cat)}
            >
              <span className="form-label" style={{ margin: 0 }}>
                {CATEGORY_LABELS[cat] ?? cat}
              </span>
              <span className="text-xs text-secondary">{isOpen ? '▲' : '▼'}</span>
            </button>
            {isOpen && (
              <div style={{ marginTop: '0.5rem' }}>
                {catTechniques.map(tech => {
                  const ov = overrideDraft[tech.id] ?? {}
                  const tempPlaceholder = tech.default_temperature != null
                    ? String(tech.default_temperature)
                    : '0.3 (provider default)'
                  return (
                    <div
                      key={tech.id}
                      className="form-section"
                      style={{ paddingLeft: '0.5rem', borderLeft: '2px solid var(--border-subtle, #2a2a3a)', marginBottom: '0.75rem' }}
                    >
                      <label className="form-label" style={{ marginBottom: '0.25rem' }}>
                        {tech.name}
                      </label>
                      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
                        {/* Model: dropdown if we have models, else text input */}
                        {analysisModels.length > 0 ? (
                          <ModelSelect
                            id={`tech-model-${tech.id}`}
                            models={analysisModels}
                            value={ov.model ?? ''}
                            placeholder=""
                            onChange={val => setOverride(tech.id, { model: val || null })}
                          />
                        ) : (
                          <input
                            id={`tech-model-${tech.id}`}
                            type="text"
                            className="model-override-input"
                            style={{ flex: '1 1 180px' }}
                            value={ov.model ?? ''}
                            onChange={(e: ChangeEvent<HTMLInputElement>) =>
                              setOverride(tech.id, { model: e.target.value || null })
                            }
                            placeholder="model (blank = provider default)"
                          />
                        )}
                        {/* Temperature */}
                        <input
                          id={`tech-temp-${tech.id}`}
                          type="number"
                          className="model-override-input"
                          style={{ flex: '0 0 120px', minWidth: '100px' }}
                          step="0.1"
                          min="0"
                          max="2"
                          value={ov.temperature ?? ''}
                          onChange={(e: ChangeEvent<HTMLInputElement>) => {
                            const raw = e.target.value
                            setOverride(tech.id, {
                              temperature: raw === '' ? null : parseFloat(raw),
                            })
                          }}
                          placeholder={tempPlaceholder}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}

      <div className="settings-key-edit-actions" style={{ marginTop: '0.5rem' }}>
        <button
          className="btn-primary settings-btn-sm"
          onClick={handleSave}
          disabled={saveStatus === 'saving'}
        >
          {saveStatus === 'saving' ? 'Saving...' : 'Save Overrides'}
        </button>
        {activeCount > 0 && (
          <button
            className="btn-secondary settings-btn-sm settings-btn-danger"
            onClick={handleClearAll}
            disabled={saveStatus === 'saving'}
          >
            Clear All
          </button>
        )}
        {saveStatus === 'saved' && (
          <span className="settings-test-result settings-test-ok text-xs">Saved</span>
        )}
        {saveStatus === 'error' && saveError && (
          <span className="settings-test-result settings-test-fail text-xs">{saveError}</span>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// AdversarialSettingsCard
// ---------------------------------------------------------------------------

/**
 * Settings card for configuring persistent adversarial analysis defaults.
 *
 * Allows users to set default enabled/mode/rounds and challenger/investigator
 * provider+model overrides. These are stored in ~/.sat/config.json under the
 * 'adversarial' key and picked up by build_adversarial_config() on every run.
 *
 * The investigator section is only shown when mode is "trident" since dual mode
 * uses only a challenger. Provider dropdowns fetch model lists via useModels()
 * to populate the model selector. When no provider is selected, the model
 * selector is disabled.
 *
 * This card has its own independent save lifecycle — changes here do not
 * interact with the provider Save Settings button at the bottom of the page.
 *
 * @decision DEC-ADVERSARIAL-SETTINGS-UI-001
 * @title AdversarialSettingsCard: independent save, full replacement on save
 * @status accepted
 * @rationale Consistent with WritingStyleCard and TechniqueOverridesCard patterns.
 *   The adversarial section is a full replacement on PUT (not field-by-field merge)
 *   so the user can clear provider/model overrides by blanking them and saving.
 *   Draft state is initialized once from server data to prevent React Query
 *   background refetches from clobbering in-flight edits.
 */
function AdversarialSettingsCard() {
  const { data: settings } = useSettings()
  const queryClient = useQueryClient()
  const { client } = useApiContext()

  // Local draft state
  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [mode, setMode] = useState<string>('')
  const [rounds, setRounds] = useState<string>('')
  const [challengerProvider, setChallengerProvider] = useState<string>('')
  const [challengerModel, setChallengerModel] = useState<string>('')
  const [investigatorProvider, setInvestigatorProvider] = useState<string>('')
  const [investigatorModel, setInvestigatorModel] = useState<string>('')

  // Initialize from server data (once, so in-flight edits are not clobbered)
  const [initialized, setInitialized] = useState(false)
  useEffect(() => {
    if (!initialized && settings) {
      const adv: AdversarialSettings | null | undefined = settings.adversarial
      setEnabled(adv?.enabled ?? null)
      setMode(adv?.mode ?? '')
      setRounds(adv?.rounds != null ? String(adv.rounds) : '')
      setChallengerProvider(adv?.challenger_provider ?? '')
      setChallengerModel(adv?.challenger_model ?? '')
      setInvestigatorProvider(adv?.investigator_provider ?? '')
      setInvestigatorModel(adv?.investigator_model ?? '')
      setInitialized(true)
    }
  }, [initialized, settings])

  // Fetch model lists for the selected providers
  const { models: challengerModels } = useModels(challengerProvider, !!challengerProvider)
  const { models: investigatorModels } = useModels(investigatorProvider, !!investigatorProvider)

  // Save state
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [saveError, setSaveError] = useState<string | null>(null)

  const providers = settings?.providers ?? {}

  // Badge: "Configured" if any adversarial setting is non-empty
  const isConfigured = !!(
    enabled != null ||
    mode ||
    rounds ||
    challengerProvider ||
    challengerModel ||
    investigatorProvider ||
    investigatorModel
  )

  async function handleSave() {
    if (!client) return
    setSaveStatus('saving')
    setSaveError(null)
    try {
      // Build adversarial object — strip empty strings to undefined
      const adversarial: AdversarialSettings = {
        enabled: enabled,
        mode: mode || undefined,
        rounds: rounds ? Number(rounds) : undefined,
        challenger_provider: challengerProvider || undefined,
        challenger_model: challengerModel || undefined,
        investigator_provider: investigatorProvider || undefined,
        investigator_model: investigatorModel || undefined,
      }

      // Build providers payload (preserve existing — no API keys, just models)
      const providerPayload: Record<string, { api_key: string; default_model: string; research_model: string }> = {}
      for (const [name, info] of Object.entries(providers)) {
        providerPayload[name] = {
          api_key: '',
          default_model: info.default_model,
          research_model: info.research_model,
        }
      }

      await client.updateSettings({ providers: providerPayload, adversarial })
      setSaveStatus('saved')
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      setTimeout(() => setSaveStatus('idle'), 2500)
    } catch (err) {
      setSaveStatus('error')
      setSaveError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleClear() {
    if (!client) return
    setSaveStatus('saving')
    setSaveError(null)
    try {
      setEnabled(null)
      setMode('')
      setRounds('')
      setChallengerProvider('')
      setChallengerModel('')
      setInvestigatorProvider('')
      setInvestigatorModel('')

      const providerPayload: Record<string, { api_key: string; default_model: string; research_model: string }> = {}
      for (const [name, info] of Object.entries(providers)) {
        providerPayload[name] = {
          api_key: '',
          default_model: info.default_model,
          research_model: info.research_model,
        }
      }

      await client.updateSettings({ providers: providerPayload, adversarial: null })
      setSaveStatus('saved')
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      setTimeout(() => setSaveStatus('idle'), 2500)
    } catch (err) {
      setSaveStatus('error')
      setSaveError(err instanceof Error ? err.message : String(err))
    }
  }

  const showInvestigator = mode === 'trident'

  return (
    <div className="settings-provider-card">
      <div className="settings-provider-header">
        <div className="settings-provider-name-row">
          <span className="settings-provider-name">Adversarial Analysis</span>
          <span className={`intel-badge ${isConfigured ? 'badge-cyan' : 'badge-green'}`}>
            {isConfigured ? 'Configured' : 'Default'}
          </span>
        </div>
      </div>

      <div className="form-section">
        <span className="form-label-hint text-xs">
          Configure adversarial critique and investigation models. Leave blank to auto-detect.
        </span>
      </div>

      {/* Enabled toggle */}
      <div className="form-section form-section-spaced">
        <label className="form-label">Enabled</label>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <input
            type="checkbox"
            id="adv-enabled"
            checked={enabled === true}
            onChange={(e: ChangeEvent<HTMLInputElement>) =>
              setEnabled(e.target.checked ? true : null)
            }
          />
          <label htmlFor="adv-enabled" className="text-xs text-secondary">
            {enabled === true ? 'On by default' : 'Use per-run setting'}
          </label>
        </div>
      </div>

      {/* Mode radio */}
      <div className="form-section form-section-spaced">
        <label className="form-label">Mode</label>
        <div className="form-radio-row">
          <label className="form-radio-label">
            <input
              type="radio"
              name="adv-mode"
              value="dual"
              checked={mode === 'dual'}
              onChange={() => setMode('dual')}
            />
            Dual
          </label>
          <label className="form-radio-label">
            <input
              type="radio"
              name="adv-mode"
              value="trident"
              checked={mode === 'trident'}
              onChange={() => setMode('trident')}
            />
            Trident
          </label>
          <label className="form-radio-label">
            <input
              type="radio"
              name="adv-mode"
              value=""
              checked={mode === ''}
              onChange={() => setMode('')}
            />
            Auto
          </label>
        </div>
      </div>

      {/* Rounds */}
      <div className="form-section form-section-spaced">
        <label className="form-label" htmlFor="adv-rounds">Rounds</label>
        <input
          id="adv-rounds"
          type="number"
          className="model-override-input"
          style={{ width: '80px' }}
          min="1"
          max="5"
          value={rounds}
          onChange={(e: ChangeEvent<HTMLInputElement>) => setRounds(e.target.value)}
          placeholder="1–5"
        />
      </div>

      {/* Challenger */}
      <div className="form-section form-section-spaced">
        <label className="form-label">Challenger</label>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <select
            className="model-override-input"
            style={{ flex: '0 0 140px' }}
            value={challengerProvider}
            onChange={(e: ChangeEvent<HTMLSelectElement>) => {
              setChallengerProvider(e.target.value)
              setChallengerModel('')
            }}
          >
            <option value="">Auto-detect</option>
            <option value="anthropic">Anthropic</option>
            <option value="openai">OpenAI</option>
            <option value="gemini">Gemini</option>
            <option value="ollama">Ollama</option>
            <option value="lmstudio">LM Studio</option>
          </select>
          {challengerProvider && challengerModels.analysis.length > 0 ? (
            <ModelSelect
              id="adv-challenger-model"
              models={challengerModels.analysis}
              value={challengerModel}
              placeholder="model (blank = provider default)"
              onChange={(val: string) => setChallengerModel(val)}
            />
          ) : (
            <input
              id="adv-challenger-model"
              type="text"
              className="model-override-input"
              style={{ flex: '1 1 180px' }}
              value={challengerModel}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setChallengerModel(e.target.value)}
              placeholder={challengerProvider ? 'model (blank = provider default)' : 'select provider first'}
              disabled={!challengerProvider}
            />
          )}
        </div>
      </div>

      {/* Investigator — only shown when mode is trident */}
      {showInvestigator && (
        <div className="form-section form-section-spaced">
          <label className="form-label">Investigator</label>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <select
              className="model-override-input"
              style={{ flex: '0 0 140px' }}
              value={investigatorProvider}
              onChange={(e: ChangeEvent<HTMLSelectElement>) => {
                setInvestigatorProvider(e.target.value)
                setInvestigatorModel('')
              }}
            >
              <option value="">Auto-detect</option>
              <option value="anthropic">Anthropic</option>
              <option value="openai">OpenAI</option>
              <option value="gemini">Gemini</option>
              <option value="ollama">Ollama</option>
              <option value="lmstudio">LM Studio</option>
            </select>
            {investigatorProvider && investigatorModels.analysis.length > 0 ? (
              <ModelSelect
                id="adv-investigator-model"
                models={investigatorModels.analysis}
                value={investigatorModel}
                placeholder="model (blank = provider default)"
                onChange={(val: string) => setInvestigatorModel(val)}
              />
            ) : (
              <input
                id="adv-investigator-model"
                type="text"
                className="model-override-input"
                style={{ flex: '1 1 180px' }}
                value={investigatorModel}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setInvestigatorModel(e.target.value)}
                placeholder={investigatorProvider ? 'model (blank = provider default)' : 'select provider first'}
                disabled={!investigatorProvider}
              />
            )}
          </div>
        </div>
      )}

      <div className="settings-key-edit-actions" style={{ marginTop: '0.5rem' }}>
        <button
          className="btn-primary settings-btn-sm"
          onClick={handleSave}
          disabled={saveStatus === 'saving'}
        >
          {saveStatus === 'saving' ? 'Saving...' : 'Save'}
        </button>
        {isConfigured && (
          <button
            className="btn-secondary settings-btn-sm settings-btn-danger"
            onClick={handleClear}
            disabled={saveStatus === 'saving'}
          >
            Clear All
          </button>
        )}
        {saveStatus === 'saved' && (
          <span className="settings-test-result settings-test-ok text-xs">Saved</span>
        )}
        {saveStatus === 'error' && saveError && (
          <span className="settings-test-result settings-test-fail text-xs">{saveError}</span>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ReportTemplatesCard
// ---------------------------------------------------------------------------

/**
 * Settings card for managing custom Jinja2 report templates.
 *
 * Shows the current template status (Default vs Custom), provides an upload
 * button (accepts .j2 and .html files), and a Revert to Default button when
 * a custom template exists. Brief requirements info helps users craft valid
 * templates.
 *
 * @decision DEC-TEMPLATE-004
 * @title ReportTemplatesCard uses React Query for template list + mutations
 * @status accepted
 * @rationale Consistent with other settings data patterns — useQuery for the
 * list, useMutation for upload/delete. The file input is uncontrolled (ref)
 * so the browser's native file picker handles selection without React state
 * thrash on every keystroke. The input is reset after each upload attempt so
 * the same file can be re-uploaded after edits.
 */
function ReportTemplatesCard() {
  const { client } = useApiContext()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null)

  const { data: templates = [], isLoading } = useQuery({
    queryKey: ['templates'],
    queryFn: () => client.getTemplates(),
  })

  const uploadMutation = useMutation({
    mutationFn: (file: File) => client.uploadTemplate(file),
    onSuccess: (result) => {
      setUploadError(null)
      setUploadSuccess(`Uploaded ${result.filename} (${result.size} bytes)`)
      queryClient.invalidateQueries({ queryKey: ['templates'] })
      if (fileInputRef.current) fileInputRef.current.value = ''
      setTimeout(() => setUploadSuccess(null), 3000)
    },
    onError: (err: Error) => {
      setUploadSuccess(null)
      // Extract detail from FastAPI JSON error body if present
      const msg = err.message ?? String(err)
      const match = msg.match(/"detail"\s*:\s*"([^"]+)"/)
      setUploadError(match ? match[1] : msg)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (filename: string) => client.deleteTemplate(filename),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['templates'] })
    },
  })

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadError(null)
    setUploadSuccess(null)
    uploadMutation.mutate(file)
  }

  const customTemplates = templates.filter((t: TemplateInfo) => t.is_custom)
  const hasCustom = customTemplates.length > 0

  return (
    <div className="settings-provider-card">
      <div className="settings-provider-header">
        <div className="settings-provider-name-row">
          <span className="settings-provider-name">Report Templates</span>
          <span className={`intel-badge ${hasCustom ? 'badge-cyan' : 'badge-green'}`}>
            {hasCustom ? 'Custom' : 'Default'}
          </span>
        </div>
      </div>

      <div className="form-section form-section-spaced">
        <label className="form-label">Template Status</label>
        {isLoading ? (
          <span className="text-secondary text-xs">Loading templates...</span>
        ) : hasCustom ? (
          <div>
            {customTemplates.map((t: TemplateInfo) => (
              <div key={t.filename} className="settings-key-row">
                <span className="text-xs text-secondary font-mono">{t.filename}</span>
                <span className="text-xs text-secondary">{(t.size / 1024).toFixed(1)} KB</span>
              </div>
            ))}
          </div>
        ) : (
          <span className="text-xs text-secondary">Using built-in default templates</span>
        )}
      </div>

      <div className="form-section form-section-spaced">
        <label className="form-label">Upload Custom Template</label>
        <span className="form-label-hint text-xs">
          Jinja2 template (.j2 or .html). Max 1 MB. Variables: question, bottom_line_assessment,
          key_findings, techniques, date, and more. See default templates for reference.
        </span>
        <div className="settings-key-edit-actions" style={{ marginTop: '0.5rem' }}>
          <input
            ref={fileInputRef}
            type="file"
            accept=".j2,.html"
            style={{ display: 'none' }}
            onChange={handleFileChange}
          />
          <button
            className="btn-secondary settings-btn-sm"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadMutation.isPending}
          >
            {uploadMutation.isPending ? 'Uploading...' : 'Choose Template File'}
          </button>
          {hasCustom && (
            <button
              className="btn-secondary settings-btn-sm settings-btn-danger"
              onClick={() => {
                customTemplates.forEach((t: TemplateInfo) => deleteMutation.mutate(t.filename))
              }}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? 'Reverting...' : 'Revert to Default'}
            </button>
          )}
        </div>
        {uploadError && (
          <div className="settings-test-result settings-test-fail text-xs" style={{ marginTop: '0.5rem' }}>
            {uploadError}
          </div>
        )}
        {uploadSuccess && (
          <div className="settings-test-result settings-test-ok text-xs" style={{ marginTop: '0.5rem' }}>
            {uploadSuccess}
          </div>
        )}
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
  /** When true, hide the API key section (Ollama ignores auth). */
  hideApiKey?: boolean
  /** Local native HTTP providers — show Base URL + always allow Test Connection. */
  isLocal?: boolean
  info: ProviderSettingsResponse
  draft: ProviderDraft
  testState: TestState
  onStartEditKey: () => void
  onCancelEditKey: () => void
  onKeyChange: (value: string) => void
  onModelChange: (value: string) => void
  onResearchModelChange: (value: string) => void
  onBaseUrlChange: (value: string) => void
  onRemoveKey: () => void
  onTestProvider: () => void
  onToggleShowKey: () => void
}

function ProviderCard({
  name,
  label,
  modelPlaceholder,
  hideModel = false,
  hideApiKey = false,
  isLocal = false,
  info,
  draft,
  testState,
  onStartEditKey,
  onCancelEditKey,
  onKeyChange,
  onModelChange,
  onResearchModelChange,
  onBaseUrlChange,
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
            {isConnected ? (isLocal ? 'Server reachable' : 'Connected') : (isLocal ? 'Server offline' : 'Not configured')}
          </span>
        </div>
        <div className="settings-provider-dot-row">
          <span className={`status-dot ${isConnected ? 'status-dot-ok' : 'status-dot-error'}`} />
        </div>
      </div>

      {/* Base URL for local providers */}
      {isLocal && (
        <div className="form-section form-section-spaced">
          <label className="form-label" htmlFor={`base-url-${name}`}>Base URL</label>
          <input
            id={`base-url-${name}`}
            type="text"
            className="model-override-input"
            value={draft.base_url || DEFAULT_BASE_URLS[name] || ''}
            onChange={(e: ChangeEvent<HTMLInputElement>) => onBaseUrlChange(e.target.value)}
            placeholder={DEFAULT_BASE_URLS[name]}
            autoComplete="off"
            spellCheck={false}
          />
          <p className="text-muted text-xs" style={{ marginTop: '0.35rem' }}>
            Native API host (no OpenAI-compat /v1 path). Default: {DEFAULT_BASE_URLS[name]}
          </p>
          <div className="settings-key-edit-actions" style={{ marginTop: '0.5rem' }}>
            <button
              className="btn-secondary settings-btn-sm"
              onClick={onTestProvider}
              disabled={testState.loading}
              type="button"
            >
              {testState.loading ? 'Testing...' : 'Test Connection'}
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

      {/* API Key section — hidden for Ollama; optional token for LM Studio */}
      {!hideApiKey && (
      <div className="form-section form-section-spaced">
        <label className="form-label" htmlFor={`key-${name}`}>
          {isLocal ? 'API Token (optional)' : 'API Key'}
        </label>

        {!isEditingKey && info.api_key_preview && (
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

        {!isEditingKey && !info.api_key_preview && (
          <button className="btn-secondary settings-btn-sm" onClick={onStartEditKey}>
            {isLocal ? 'Add API Token' : 'Add API Key'}
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
                placeholder={isLocal ? `Optional ${label} token` : `Enter ${label} API key`}
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
              {(draft.api_key || isLocal) && (
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
            {testState.result && !isLocal && (
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
      )}

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

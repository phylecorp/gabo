/**
 * @decision DEC-DESKTOP-NEW-ANALYSIS-001
 * @title NewAnalysis: full config form with staged options and submit-to-navigate
 * @status accepted
 * @rationale The form is organized top-to-bottom by importance: question first
 *   (required), evidence second (often provided), techniques third (has smart
 *   default), provider fourth (set-and-forget), advanced options last (rarely
 *   changed). On submit we navigate to the run detail page immediately after
 *   the API responds with a run_id — the RunDetail page handles live progress
 *   via WebSocket. This keeps the concern separation clean: NewAnalysis owns
 *   configuration, RunDetail owns progress tracking.
 *
 * @decision DEC-DESKTOP-NEW-ANALYSIS-CURATION-001
 * @title NewAnalysis: multi-step form with optional evidence curation path
 * @status accepted
 * @rationale Added a second submit path ("Gather & Review Evidence") that transitions
 *   through gather → review steps before starting analysis. The existing single-shot
 *   "Run Analysis" flow is preserved unchanged. Step state is local to this component;
 *   the useEvidenceGathering hook owns WS lifecycle and pool curation.
 *
 * @decision DEC-DESKTOP-NEW-ANALYSIS-POOL-001
 * @title "Run Analysis" routes through evidence review when evidence text or sources are present
 * @status accepted
 * @rationale When the user provides evidence (text or document sources) and clicks "Run
 *   Analysis", the app calls POST /api/evidence/pool to create a real EvidenceSession on
 *   the backend synchronously (no WebSocket), then shows the EvidenceReview step before
 *   running analysis via the curated path. This ensures evidence is always reviewed before
 *   analysis when the user has supplied it. The zero-evidence quick path (question-only with
 *   research) continues to call startAnalysis() directly. The "Gather & Review Evidence"
 *   button path is unchanged.
 *
 * @decision DEC-UPLOAD-004
 * @title SourceInput placed below evidence textarea; sources passed to both submit paths
 * @status accepted
 * @rationale evidence_sources is a list of file paths/URLs the backend ingests before
 *   analysis runs. It is separate from the free-text evidence field (which is pasted
 *   inline text). Both the direct "Run Analysis" path and the "Gather & Review" path
 *   receive sources so the ingestion pipeline runs regardless of which path is chosen.
 *   For the curated path: sources are sent in the gather request (stored on the session)
 *   AND in the final analyze request. The backend resolves them as: request sources take
 *   precedence; session-stored sources are the fallback. This double-wiring ensures
 *   sources are never silently dropped regardless of client implementation.
 */
import { useState, useEffect, type FormEvent } from 'react'
import { useNavigate, useLocation } from 'react-router'
import { useAnalysis } from '../hooks/useAnalysis'
import { useConcurrencyStatus } from '../hooks/useRuns'
import { useEvidenceGathering } from '../hooks/useEvidenceGathering'
import { useTechniques } from '../hooks/useTechniques'
import { useProviders } from '../hooks/useProviders'
import { useApiContext } from '../api/context'
import { SatClient } from '../api/client'
import QuestionInput from '../components/analysis/QuestionInput'
import TechniqueSelector from '../components/analysis/TechniqueSelector'
import ProviderConfig from '../components/analysis/ProviderConfig'
import SourceInput from '../components/analysis/SourceInput'
import EvidenceGatheringProgress from '../components/evidence/EvidenceGatheringProgress'
import EvidenceReview from '../components/evidence/EvidenceReview'

type Step = 'configure' | 'gathering' | 'review'

export default function NewAnalysis() {
  const navigate = useNavigate()
  const location = useLocation()
  const prefill = (location.state as Record<string, unknown>)?.prefill as {
    question?: string
    techniques?: string[]
    adversarialEnabled?: boolean
  } | undefined
  const { baseUrl } = useApiContext()
  const { startAnalysis } = useAnalysis()
  const { data: concurrency } = useConcurrencyStatus()
  const {
    gatherEvidence,
    setPrebuiltPool,
    progress: gatherProgress,
    evidencePool,
    sessionId: evidenceSessionId,
    toggleItem,
    selectAll,
    deselectAll,
    selectByFilter,
    selectedCount,
    totalCount,
    reset: resetEvidence,
  } = useEvidenceGathering()

  const { data: techniques = [] } = useTechniques()
  const { data: providers = [] } = useProviders()

  // Step state
  const [step, setStep] = useState<Step>('configure')

  // Core form state
  const [name, setName] = useState('')
  const [question, setQuestion] = useState(prefill?.question ?? '')
  const [evidence, setEvidence] = useState('')
  const [selectedTechniques, setSelectedTechniques] = useState<string[]>(prefill?.techniques ?? [])

  // Provider/model
  const defaultProvider = providers.find(p => p.has_api_key)?.name ?? ''
  const [provider, setProvider] = useState('')
  const [modelOverride, setModelOverride] = useState('')

  // Source documents (file paths and URLs)
  const [sources, setSources] = useState<string[]>([])

  // Advanced section visibility
  const [advancedOpen, setAdvancedOpen] = useState(false)

  // Advanced toggles
  const [researchEnabled, setResearchEnabled] = useState(true)
  const [researchMode, setResearchMode] = useState<'multi' | 'single'>('multi')
  const [adversarialEnabled, setAdversarialEnabled] = useState(prefill?.adversarialEnabled ?? true)
  const [adversarialMode, setAdversarialMode] = useState<'dual' | 'trident'>('dual')
  const [adversarialRounds, setAdversarialRounds] = useState(1)
  const [reportEnabled, setReportEnabled] = useState(true)

  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const effectiveProvider = provider || defaultProvider

  // Resolve the model to send in requests: manual override wins, then the
  // provider's saved default_model (which the backend returns from config.json),
  // then null (backend will apply its own fallback chain).
  const selectedProviderInfo = providers.find(p => p.name === effectiveProvider)
  const effectiveModel = modelOverride.trim() || selectedProviderInfo?.default_model || null

  const canSubmit = question.trim().length > 0 && !submitting
  const canGather = question.trim().length > 0 && !submitting && (evidence.trim().length > 0 || researchEnabled)

  // Auto-recover step from active evidence session (survives navigation)
  useEffect(() => {
    if (step === 'configure') {
      if (gatherProgress.status === 'gathering') {
        setStep('gathering')
      } else if (gatherProgress.status === 'ready' && evidencePool) {
        setStep('review')
      }
    }
  }, []) // Only on mount — don't fight user-initiated step changes

  // Auto-transition from gathering → review when pool is ready
  useEffect(() => {
    if (step === 'gathering' && gatherProgress.status === 'ready') {
      setStep('review')
    }
    if (step === 'gathering' && gatherProgress.status === 'failed') {
      setError(gatherProgress.error ?? 'Evidence gathering failed')
      setStep('configure')
    }
  }, [step, gatherProgress.status, gatherProgress.error])

  // --- Direct single-shot analysis (or routes to review when evidence present) ---
  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    setError(null)
    setSubmitting(true)

    const hasEvidence = evidence.trim().length > 0 || sources.length > 0

    // When evidence text or document sources are present, create an EvidencePool
    // on the backend and show the review step before running analysis (DEC-DESKTOP-NEW-ANALYSIS-POOL-001).
    if (hasEvidence && baseUrl) {
      try {
        const client = new SatClient(baseUrl)
        const { session_id, pool } = await client.createEvidencePool({
          question: question.trim(),
          name: name.trim() || undefined,
          evidence: evidence.trim() || undefined,
          evidence_sources: sources.length > 0 ? sources : undefined,
        })
        setPrebuiltPool(pool, session_id)
        setStep('review')
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to create evidence pool')
      } finally {
        setSubmitting(false)
      }
      return
    }

    // Zero-evidence quick path: question-only with research → run analysis directly.
    try {
      const runId = await startAnalysis({
        question: question.trim(),
        name: name.trim() || null,
        evidence: null,
        techniques: selectedTechniques.length > 0 ? selectedTechniques : null,
        provider: effectiveProvider || undefined,
        model: effectiveModel,
        research_enabled: researchEnabled,
        research_mode: researchEnabled ? researchMode : undefined,
        adversarial_enabled: adversarialEnabled,
        adversarial_mode: adversarialEnabled ? adversarialMode : undefined,
        adversarial_rounds: adversarialEnabled ? adversarialRounds : undefined,
        report_enabled: reportEnabled,
        evidence_sources: undefined,
      })

      if (runId) {
        navigate(`/runs/${runId}`, { state: { liveSession: true } })
      } else {
        setError('Failed to start analysis — no run ID returned')
        setSubmitting(false)
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start analysis')
      setSubmitting(false)
    }
  }

  // --- Gather & Review path ---
  async function handleGather() {
    if (!canGather) return
    setError(null)
    setSubmitting(true)

    try {
      await gatherEvidence({
        question: question.trim(),
        name: name.trim() || null,
        evidence: evidence.trim() || null,
        research_enabled: researchEnabled,
        research_mode: researchEnabled ? researchMode : undefined,
        provider: effectiveProvider || undefined,
        model: effectiveModel,
        evidence_sources: sources.length > 0 ? sources : undefined,
      })
      setStep('gathering')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start evidence gathering')
    } finally {
      setSubmitting(false)
    }
  }

  // --- Submit curated analysis ---
  async function handleCuratedSubmit() {
    if (!evidenceSessionId || !baseUrl) return
    setError(null)
    setSubmitting(true)

    try {
      const client = new SatClient(baseUrl)
      const response = await client.analyzeWithCuratedEvidence(evidenceSessionId, {
        selected_item_ids: evidencePool?.items
          .filter(i => i.selected)
          .map(i => i.item_id) ?? [],
        name: name.trim() || null,
        techniques: selectedTechniques.length > 0 ? selectedTechniques : null,
        provider: effectiveProvider || undefined,
        model: effectiveModel,
        adversarial_enabled: adversarialEnabled,
        adversarial_mode: adversarialEnabled ? adversarialMode : undefined,
        adversarial_rounds: adversarialEnabled ? adversarialRounds : undefined,
        report_enabled: reportEnabled,
        evidence_sources: sources.length > 0 ? sources : undefined,
      })

      navigate(`/runs/${response.run_id}`, { state: { liveSession: true } })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start analysis')
      setSubmitting(false)
    }
  }

  function handleBackFromReview() {
    resetEvidence()
    setStep('configure')
    setSubmitting(false)
    setError(null)
  }

  // -------------------------------------------------------------------------
  // Render: gathering step
  // -------------------------------------------------------------------------
  if (step === 'gathering') {
    return (
      <div className="new-analysis">
        <div className="new-analysis-header">
          <h2 className="new-analysis-title">Evidence Gathering</h2>
          <span className="new-analysis-subtitle text-muted text-xs">
            Collecting and structuring evidence for review
          </span>
        </div>
        <EvidenceGatheringProgress progress={gatherProgress} />
      </div>
    )
  }

  // -------------------------------------------------------------------------
  // Render: review step
  // -------------------------------------------------------------------------
  if (step === 'review' && evidencePool) {
    return (
      <div className="new-analysis">
        <div className="new-analysis-header">
          <h2 className="new-analysis-title">Review Evidence</h2>
          <span className="new-analysis-subtitle text-muted text-xs">
            Select the evidence items to include in your analysis
          </span>
        </div>
        {error && (
          <div className="form-error form-error-spaced">
            <span className="intel-badge badge-red">Error</span>
            <span className="text-sm text-secondary">{error}</span>
          </div>
        )}
        <EvidenceReview
          pool={evidencePool}
          selectedCount={selectedCount}
          totalCount={totalCount}
          onToggleItem={toggleItem}
          onSelectAll={selectAll}
          onDeselectAll={deselectAll}
          onSelectByFilter={selectByFilter}
          onSubmit={handleCuratedSubmit}
          onBack={handleBackFromReview}
          submitting={submitting}
        />
      </div>
    )
  }

  // -------------------------------------------------------------------------
  // Render: configure step (default)
  // -------------------------------------------------------------------------
  return (
    <div className="new-analysis">
      <div className="new-analysis-header">
        <h2 className="new-analysis-title">Configure Analysis</h2>
        <span className="new-analysis-subtitle text-muted text-xs">
          Define your intelligence question and select analytical techniques
        </span>
      </div>

      {/* Concurrency warning banner: show when analyses are running and new will queue */}
      {concurrency && (concurrency.running >= concurrency.max_concurrent) && (
        <div className="new-analysis-queue-warning" role="alert">
          <span className="queue-warning-icon">⏳</span>
          <span className="queue-warning-text">
            {concurrency.running} analysis running — your analysis will be queued and start automatically when a slot opens.
            {concurrency.queued > 0 && ` (${concurrency.queued} already queued)`}
          </span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="new-analysis-form">
        {/* Analysis Name */}
        <div className="form-section">
          <label className="form-label">
            Analysis Name
            <span className="form-label-hint"> (optional)</span>
          </label>
          <input
            type="text"
            className="form-input"
            placeholder="Short label for this analysis"
            value={name}
            onChange={e => setName(e.target.value)}
            disabled={submitting}
            maxLength={100}
          />
        </div>

        {/* Question */}
        <div className="form-section">
          <QuestionInput
            value={question}
            onChange={setQuestion}
            disabled={submitting}
          />
        </div>

        {/* Evidence */}
        <div className="form-section">
          <label className="form-label">
            Evidence
            <span className="form-label-hint"> (optional)</span>
          </label>
          <textarea
            className="evidence-textarea"
            placeholder="Paste relevant intelligence, reports, or source material here. Each piece can be separated by --- or newlines."
            value={evidence}
            onChange={e => setEvidence(e.target.value)}
            disabled={submitting}
            rows={5}
          />
          <div className="form-field-meta text-xs text-muted">
            {evidence.length > 0 ? `${evidence.length} chars` : 'No evidence provided — techniques will apply general analytical frameworks'}
          </div>
        </div>

        {/* Source Documents */}
        <div className="form-section">
          <label className="form-label">Source Documents</label>
          <SourceInput sources={sources} onChange={setSources} disabled={submitting} />
          <span className="text-xs text-muted form-hint">
            Add files or URLs to ingest as evidence. Supports PDF, DOCX, HTML, images, and more.
          </span>
        </div>

        {/* Techniques */}
        {techniques.length > 0 && (
          <div className="form-section">
            <TechniqueSelector
              techniques={techniques}
              selected={selectedTechniques}
              onChange={setSelectedTechniques}
              disabled={submitting}
            />
          </div>
        )}

        {/* Advanced options */}
        <div className="form-section form-section-advanced">
          <div
            className="form-advanced-header form-advanced-header-toggle"
            onClick={() => setAdvancedOpen(o => !o)}
          >
            <span className="form-label">Advanced Options</span>
            <span className="form-advanced-chevron" aria-hidden="true">
              {advancedOpen ? '▾' : '▸'}
            </span>
          </div>

          {advancedOpen && (
            <>
              {/* LLM Provider */}
              {providers.length > 0 && (
                <ProviderConfig
                  providers={providers}
                  selected={effectiveProvider}
                  onSelect={setProvider}
                  model={modelOverride}
                  onModelChange={setModelOverride}
                  disabled={submitting}
                />
              )}

              {/* Research */}
              <div className="form-toggle-row">
                <label className="form-toggle-label">
                  <input
                    type="checkbox"
                    checked={researchEnabled}
                    onChange={e => setResearchEnabled(e.target.checked)}
                    disabled={submitting}
                    className="form-checkbox"
                  />
                  <span className="form-toggle-name">Web Research</span>
                  <span className="form-toggle-desc text-muted text-xs">
                    Query external research providers for current intelligence
                  </span>
                </label>
                {researchEnabled && (
                  <div className="form-toggle-sub">
                    <label className="form-sub-label">Mode</label>
                    <div className="form-radio-row">
                      {(['multi', 'single'] as const).map(m => (
                        <label key={m} className="form-radio-label">
                          <input
                            type="radio"
                            name="researchMode"
                            value={m}
                            checked={researchMode === m}
                            onChange={() => setResearchMode(m)}
                            disabled={submitting}
                          />
                          <span className="text-sm">{m}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Adversarial */}
              <div className="form-toggle-row">
                <label className="form-toggle-label">
                  <input
                    type="checkbox"
                    checked={adversarialEnabled}
                    onChange={e => setAdversarialEnabled(e.target.checked)}
                    disabled={submitting}
                    className="form-checkbox"
                  />
                  <span className="form-toggle-name">Adversarial Review</span>
                  <span className="form-toggle-desc text-muted text-xs">
                    Apply devil's advocate critique and rebuttal to each technique result
                  </span>
                </label>
                {adversarialEnabled && (
                  <div className="form-toggle-sub">
                    <div className="form-radio-row">
                      <label className="form-sub-label">Mode</label>
                      {(['dual', 'trident'] as const).map(m => (
                        <label key={m} className="form-radio-label">
                          <input
                            type="radio"
                            name="adversarialMode"
                            value={m}
                            checked={adversarialMode === m}
                            onChange={() => setAdversarialMode(m)}
                            disabled={submitting}
                          />
                          <span className="text-sm">{m}</span>
                        </label>
                      ))}
                    </div>
                    <div className="form-radio-row-nested">
                      <label className="form-sub-label">Rounds</label>
                      <input
                        type="number"
                        min={1}
                        max={5}
                        value={adversarialRounds}
                        onChange={e => setAdversarialRounds(Number(e.target.value))}
                        disabled={submitting}
                        className="form-number-input"
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* Report */}
              <div className="form-toggle-row">
                <label className="form-toggle-label">
                  <input
                    type="checkbox"
                    checked={reportEnabled}
                    onChange={e => setReportEnabled(e.target.checked)}
                    disabled={submitting}
                    className="form-checkbox"
                  />
                  <span className="form-toggle-name">Generate Report</span>
                  <span className="form-toggle-desc text-muted text-xs">
                    Produce a formatted intelligence report on completion
                  </span>
                </label>
              </div>
            </>
          )}
        </div>

        {/* Error display */}
        {error && (
          <div className="form-error">
            <span className="intel-badge badge-red">Error</span>
            <span className="text-sm text-secondary">{error}</span>
          </div>
        )}

        {/* Submit actions */}
        <div className="form-actions">
          <button
            type="submit"
            className={`btn-primary btn-lg ${!canSubmit ? 'btn-disabled' : ''}`}
            disabled={!canSubmit}
            title={!canSubmit ? (submitting ? 'Analysis already running' : 'Enter an intelligence question to continue') : 'Full pipeline: evidence → techniques → synthesis'}
          >
            {submitting ? 'Starting analysis...' : 'Run Analysis'}
          </button>
          <button
            type="button"
            className={`btn-primary btn-lg btn-gather${canGather ? '' : ' btn-disabled'}`}
            disabled={!canGather}
            onClick={handleGather}
            title={!canGather ? (submitting ? 'Analysis already running' : 'Enter an intelligence question to continue') : 'Collect and curate evidence before running techniques'}
          >
            Gather &amp; Review Evidence
          </button>
          {question.trim().length === 0 && (
            <span className="form-submit-hint text-muted text-xs">
              Enter an intelligence question to continue
            </span>
          )}
        </div>
      </form>
    </div>
  )
}

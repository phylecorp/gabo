/**
 * @decision DEC-DESKTOP-API-TYPES-001
 * @title TypeScript API types mirror Python Pydantic models verbatim
 * @status accepted
 * @rationale Single source of truth is the Python models — TypeScript types are
 *   derived from them manually (codegen considered too heavyweight for this phase).
 *   The types here cover all API shapes needed through Wave 8. When Python models
 *   change, these types must be updated in sync. Fields match field names exactly
 *   to avoid mapping layers at the fetch boundary.
 */

// Mirrors Python Pydantic models

export interface TechniqueInfo {
  id: string
  name: string
  category: 'diagnostic' | 'contrarian' | 'imaginative'
  description: string
  order: number
}

export interface ProviderInfo {
  name: string
  has_api_key: boolean
  default_model: string
}

export interface AnalysisRequest {
  question: string
  name?: string | null
  evidence?: string | null
  techniques?: string[] | null
  output_dir?: string
  provider?: string
  model?: string | null
  research_enabled?: boolean
  research_mode?: string
  adversarial_enabled?: boolean
  adversarial_mode?: string
  adversarial_rounds?: number
  report_enabled?: boolean
  report_format?: string
  evidence_sources?: string[]
}

export interface AnalysisResponse {
  run_id: string
  ws_url: string
  queue_position?: number | null
}

export interface ConcurrencyStatus {
  running: number
  queued: number
  max_concurrent: number
}

export interface Artifact {
  technique_id: string
  technique_name: string
  category: string
  markdown_path: string
  json_path: string | null
  timestamp: string
}

export interface RunSummary {
  run_id: string
  question: string
  name?: string | null
  started_at: string
  completed_at: string | null
  techniques_selected: string[]
  techniques_completed: string[]
  evidence_provided: boolean
  adversarial_enabled: boolean
  providers_used: string[]
  status: string
}

export interface RunDetail extends RunSummary {
  artifacts: Artifact[]
  synthesis_path: string | null
}

// ACH specific
export interface ACHHypothesis {
  id: string
  description: string
}

export interface ACHEvidence {
  id: string
  description: string
  credibility: 'High' | 'Medium' | 'Low'
  relevance: 'High' | 'Medium' | 'Low'
}

export interface ACHRating {
  evidence_id: string
  hypothesis_id: string
  rating: 'C' | 'I' | 'N'
  explanation: string
}

export interface ACHResult {
  technique_id: string
  technique_name: string
  summary: string
  hypotheses: ACHHypothesis[]
  evidence: ACHEvidence[]
  matrix: ACHRating[]
  inconsistency_scores: Record<string, number>
  most_likely: string
  rejected: string[]
  diagnosticity_notes: string
  missing_evidence: string[]
}

// Synthesis
export interface TechniqueFinding {
  technique_id: string
  technique_name: string
  key_finding: string
  confidence: 'High' | 'Medium' | 'Low'
}

export interface SynthesisResult {
  technique_id: string
  technique_name: string
  summary: string
  question: string
  techniques_applied: string[]
  key_findings: TechniqueFinding[]
  convergent_judgments: string[]
  divergent_signals: string[]
  highest_confidence_assessments: string[]
  remaining_uncertainties: string[]
  intelligence_gaps: string[]
  recommended_next_steps: string[]
  bottom_line_assessment: string
}

// Adversarial
export interface Challenge {
  point: string
  evidence: string
  severity: string
}

export interface CritiqueResult {
  technique_id: string
  technique_name: string
  summary: string
  agreements: string[]
  challenges: Challenge[]
  alternative_interpretations: string[]
  evidence_gaps: string[]
  severity: string
  overall_assessment: string
  revised_confidence: string
}

export interface RebuttalPoint {
  challenge: string
  rebuttal: string
  conceded: boolean
}

export interface RebuttalResult {
  technique_id: string
  technique_name: string
  summary: string
  accepted_challenges: string[]
  rejected_challenges: RebuttalPoint[]
  revised_conclusions: string
}

export interface ConvergencePoint {
  topic: string
  assessment: string
}

export interface DivergencePoint {
  topic: string
  primary_view: string
  challenger_view: string
  investigator_view?: string
}

export interface ConvergenceResult {
  technique_id: string
  technique_name: string
  summary: string
  convergence_points: ConvergencePoint[]
  divergence_points: DivergencePoint[]
  novel_insights: string[]
  confidence_delta: string
  analytical_blindspots_identified: string[]
}

// Settings
export interface ProviderSettings {
  api_key: string
  default_model: string
}

export interface AppSettings {
  providers: Record<string, ProviderSettings>
}

export interface ProviderSettingsResponse {
  has_api_key: boolean
  api_key_preview: string
  default_model: string
  source: string
}

export interface SettingsResponse {
  providers: Record<string, ProviderSettingsResponse>
}

export interface TestProviderRequest {
  provider: string
  api_key: string
  model?: string
}

export interface TestProviderResponse {
  success: boolean
  error?: string | null
  model_used?: string | null
}

// Evidence Curation
export interface EvidenceItem {
  item_id: string
  claim: string
  source: 'decomposition' | 'research' | 'user'
  source_ids: string[]
  category: string
  confidence: 'High' | 'Medium' | 'Low'
  entities: string[]
  verified: boolean
  selected: boolean
  provider_name: string | null
}

export interface EvidencePool {
  session_id: string
  question: string
  items: EvidenceItem[]
  sources: Record<string, any>[]
  gaps: string[]
  provider_summary: string
  status: 'gathering' | 'ready' | 'failed'
  error: string | null
}

export interface EvidenceGatherRequest {
  question: string
  name?: string | null
  evidence?: string | null
  research_enabled?: boolean
  research_mode?: string
  provider?: string
  model?: string | null
  evidence_sources?: string[]
}

export interface EvidenceGatherResponse {
  session_id: string
  ws_url: string
}

export interface CuratedAnalysisRequest {
  selected_item_ids: string[]
  name?: string | null
  techniques?: string[] | null
  provider?: string
  model?: string | null
  adversarial_enabled?: boolean
  adversarial_mode?: string
  adversarial_rounds?: number
  report_enabled?: boolean
  report_format?: string
  evidence_sources?: string[]
}

// Evidence gathering progress state
export interface EvidenceGatheringProgress {
  status: 'idle' | 'gathering' | 'ready' | 'failed'
  events: PipelineEventMessage[]
  researchProviders: Record<string, 'pending' | 'running' | 'completed' | 'failed'>
  error: string | null
}

// Pipeline Events (from WebSocket)
export type PipelineEventType =
  | 'ResearchStarted'
  | 'ProviderStarted'
  | 'ProviderCompleted'
  | 'ProviderFailed'
  | 'ResearchCompleted'
  | 'StageStarted'
  | 'StageCompleted'
  | 'ArtifactWritten'
  | 'run_completed'
  | 'run_failed'
  | 'EvidenceGatheringStarted'
  | 'EvidenceGatheringCompleted'
  | 'run_queued'
  | 'run_started'

export interface PipelineEventMessage {
  type: PipelineEventType
  data: Record<string, any>
  timestamp: string
}

// Run progress state (reducer)
export interface RunProgress {
  status: 'connecting' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  events: PipelineEventMessage[]
  currentStage: string | null
  currentTechnique: string | null
  completedStages: string[]
  researchProviders: Record<string, 'pending' | 'running' | 'completed' | 'failed'>
  error: string | null
  outputDir: string | null
}

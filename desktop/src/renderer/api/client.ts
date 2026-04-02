/**
 * @decision DEC-DESKTOP-API-CLIENT-001
 * @title SatClient: thin fetch wrapper with typed methods, no retry logic
 * @status accepted
 * @rationale React Query handles retry at the hook layer (configured globally
 *   with retry: 1). The client stays thin — just URL construction, JSON parsing,
 *   and error surfacing. A class is used instead of plain functions so the baseUrl
 *   is captured once per QueryClient call rather than re-read from context.
 *
 * @decision DEC-AUTH-008
 * @title SatClient accepts authToken and injects Authorization + WS token
 * @status accepted
 * @rationale The auth token is fetched once at startup and stored in ApiContext.
 *   SatClient receives it at construction time. The private request() method
 *   merges the Authorization: Bearer header into every fetch call. Direct fetch
 *   calls (getRunReport, downloadArtifact, downloadExport) also include the header.
 *   buildWsUrl() appends ?token=<token> to WebSocket URLs since the WS API does
 *   not support custom headers. Empty token (dev mode) sends no auth header,
 *   which works when the server has SAT_DISABLE_AUTH=1.
 */
import type {
  AnalysisRequest,
  AnalysisResponse,
  ConcurrencyStatus,
  TechniqueInfo,
  ProviderInfo,
  RunSummary,
  RunDetail,
  AppSettings,
  SettingsResponse,
  TestProviderRequest,
  TestProviderResponse,
  EvidenceGatherRequest,
  EvidenceGatherResponse,
  EvidenceItem,
  EvidencePool,
  CuratedAnalysisRequest,
  PoolRequest,
  PoolResponse,
  UpdateEvidenceItemRequest,
  CreateEvidenceItemRequest,
  ModelsResponse,
  TemplateInfo,
  TemplateUploadResponse,
} from './types'

export class SatClient {
  constructor(
    private baseUrl: string,
    private authToken: string = '',
  ) {}

  /** Build Authorization header object — empty if no token (dev mode). */
  private authHeaders(): Record<string, string> {
    return this.authToken ? { Authorization: `Bearer ${this.authToken}` } : {}
  }

  /**
   * Append ?token=<authToken> to a WebSocket URL for WS auth.
   * Returns the URL unchanged if no token is set.
   */
  buildWsUrl(wsUrl: string): string {
    if (!this.authToken) return wsUrl
    const separator = wsUrl.includes('?') ? '&' : '?'
    return `${wsUrl}${separator}token=${encodeURIComponent(this.authToken)}`
  }

  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...this.authHeaders(),
      },
      ...options,
      // Merge caller-provided headers on top of auth headers
      ...(options?.headers
        ? { headers: { 'Content-Type': 'application/json', ...this.authHeaders(), ...options.headers } }
        : {}),
    })
    if (!res.ok) {
      const text = await res.text()
      throw new Error(`API error ${res.status}: ${text}`)
    }
    if (res.status === 204) return undefined as T
    return res.json()
  }

  async health() {
    return this.request<{ status: string; version: string }>('/api/health')
  }

  async getTechniques() {
    return this.request<TechniqueInfo[]>('/api/techniques')
  }

  async getProviders() {
    return this.request<ProviderInfo[]>('/api/config/providers')
  }

  async startAnalysis(req: AnalysisRequest) {
    return this.request<AnalysisResponse>('/api/analysis', {
      method: 'POST',
      body: JSON.stringify(req),
    })
  }

  async getRuns(dir?: string, limit?: number) {
    const params = new URLSearchParams()
    if (dir) params.set('dir', dir)
    if (limit) params.set('limit', String(limit))
    const qs = params.toString()
    return this.request<RunSummary[]>(`/api/runs${qs ? `?${qs}` : ''}`)
  }

  async getRun(runId: string) {
    return this.request<RunDetail>(`/api/runs/${runId}`)
  }

  async getRunArtifact(runId: string, jsonPath: string) {
    return this.request<any>(`/api/runs/${runId}/artifact?path=${encodeURIComponent(jsonPath)}`)
  }

  async getRunReport(runId: string, fmt: string = 'html') {
    const res = await fetch(`${this.baseUrl}/api/runs/${runId}/report?fmt=${fmt}`, {
      headers: this.authHeaders(),
    })
    if (!res.ok) throw new Error(`Report fetch failed: ${res.status}`)
    return res.text()
  }

  async generateReport(runId: string, fmt?: string): Promise<{ paths: string[] }> {
    return this.request<{ paths: string[] }>(
      `/api/runs/${runId}/report/generate?fmt=${fmt ?? 'both'}`,
      { method: 'POST' }
    )
  }

  async downloadArtifact(runId: string, path: string): Promise<Blob> {
    const res = await fetch(
      `${this.baseUrl}/api/runs/${runId}/artifact/download?path=${encodeURIComponent(path)}`,
      { headers: this.authHeaders() }
    )
    if (!res.ok) throw new Error(`Download failed: ${res.status}`)
    return res.blob()
  }

  async downloadExport(runId: string): Promise<Blob> {
    const res = await fetch(`${this.baseUrl}/api/runs/${runId}/export`, {
      headers: this.authHeaders(),
    })
    if (!res.ok) throw new Error(`Export failed: ${res.status}`)
    return res.blob()
  }

  async deleteRun(runId: string) {
    return this.request<void>(`/api/runs/${runId}`, { method: 'DELETE' })
  }

  async renameRun(runId: string, name: string) {
    return this.request<RunSummary>(`/api/runs/${runId}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    })
  }

  async getSettings() {
    return this.request<SettingsResponse>('/api/config/settings')
  }

  async updateSettings(settings: AppSettings) {
    return this.request<SettingsResponse>('/api/config/settings', {
      method: 'PUT',
      body: JSON.stringify(settings),
    })
  }

  async testProvider(req: TestProviderRequest) {
    return this.request<TestProviderResponse>('/api/config/test-provider', {
      method: 'POST',
      body: JSON.stringify(req),
    })
  }

  async gatherEvidence(req: EvidenceGatherRequest) {
    return this.request<EvidenceGatherResponse>('/api/evidence/gather', {
      method: 'POST',
      body: JSON.stringify(req),
    })
  }

  async createEvidencePool(req: PoolRequest) {
    return this.request<PoolResponse>('/api/evidence/pool', {
      method: 'POST',
      body: JSON.stringify(req),
    })
  }

  async getEvidencePool(sessionId: string) {
    return this.request<EvidencePool>(`/api/evidence/${sessionId}`)
  }

  async analyzeWithCuratedEvidence(sessionId: string, req: CuratedAnalysisRequest) {
    return this.request<AnalysisResponse>(`/api/evidence/${sessionId}/analyze`, {
      method: 'POST',
      body: JSON.stringify(req),
    })
  }

  async getRunEvidence(runId: string): Promise<EvidencePool | null> {
    try {
      return await this.request<EvidencePool>(`/api/runs/${runId}/evidence`)
    } catch (err) {
      const msg = (err as Error).message ?? ''
      if (msg.includes('404')) return null
      throw err
    }
  }

  async cancelRun(runId: string) {
    return this.request<{ cancelled: boolean; run_id: string }>(
      `/api/runs/${runId}/cancel`,
      { method: 'POST' }
    )
  }

  async getConcurrencyStatus() {
    return this.request<ConcurrencyStatus>('/api/concurrency')
  }

  async getModels(provider: string) {
    return this.request<ModelsResponse>(`/api/config/models/${encodeURIComponent(provider)}`)
  }

  async updateEvidenceItem(
    sessionId: string,
    itemId: string,
    updates: UpdateEvidenceItemRequest,
  ): Promise<EvidenceItem> {
    return this.request<EvidenceItem>(
      `/api/evidence/${sessionId}/items/${itemId}`,
      {
        method: 'PATCH',
        body: JSON.stringify(updates),
      },
    )
  }

  async createEvidenceItem(
    sessionId: string,
    data: CreateEvidenceItemRequest,
  ): Promise<EvidenceItem> {
    return this.request<EvidenceItem>(
      `/api/evidence/${sessionId}/items`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      },
    )
  }

  /**
   * Import a complete EvidencePool verbatim into a new evidence session.
   *
   * Used by the re-analyze flow to carry evidence from a prior run forward.
   * Returns a fresh session_id — no LLM calls or ingestion are performed.
   * The pool is accepted verbatim; the prior session_id is replaced.
   *
   * @decision DEC-DESKTOP-REANALYZE-001
   * @title importEvidencePool: thin wrapper around POST /api/evidence/pool/import
   * @status accepted
   * @rationale The re-analyze flow needs to carry prior evidence into a new session
   *   synchronously. importEvidencePool maps directly to the backend import endpoint,
   *   which creates a fresh session with the prior pool's items preserved verbatim.
   *   Kept as a dedicated method (rather than reusing createEvidencePool) so call sites
   *   are semantically distinct — callers of importEvidencePool have a full EvidencePool,
   *   callers of createEvidencePool have raw text/sources that need parsing.
   */
  async importEvidencePool(pool: EvidencePool): Promise<PoolResponse> {
    return this.request<PoolResponse>('/api/evidence/pool/import', {
      method: 'POST',
      body: JSON.stringify(pool),
    })
  }

  /** List all report templates (custom + default). */
  async getTemplates(): Promise<TemplateInfo[]> {
    return this.request<TemplateInfo[]>('/api/config/templates')
  }

  /**
   * Upload a custom Jinja2 report template.
   *
   * Sends the file as multipart/form-data. The backend validates Jinja2
   * syntax and stores the file in ~/.sat/templates/ at 0o600 permissions.
   */
  async uploadTemplate(file: File): Promise<TemplateUploadResponse> {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${this.baseUrl}/api/config/templates/upload`, {
      method: 'POST',
      headers: this.authHeaders(),
      body: form,
    })
    if (!res.ok) {
      const text = await res.text()
      throw new Error(`API error ${res.status}: ${text}`)
    }
    return res.json()
  }

  /** Delete a custom report template by filename. Returns 404 if not found. */
  async deleteTemplate(filename: string): Promise<void> {
    return this.request<void>(
      `/api/config/templates/${encodeURIComponent(filename)}`,
      { method: 'DELETE' },
    )
  }
}

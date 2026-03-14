/**
 * @decision DEC-DESKTOP-HOOK-EVIDENCE-001
 * @title useEvidenceGathering: reducer-driven evidence gathering with WebSocket + local curation
 * @status accepted
 * @rationale Evidence gathering mirrors the analysis flow (POST → WS → events) but adds
 *   local curation state (toggling items). The reducer handles WS events identically to
 *   useAnalysis for research provider tracking, plus manages the EvidencePool and selection
 *   state. Selection mutations are local-only (no server round-trip needed).
 *   State now lives in EvidenceGatheringProvider (evidenceContext.tsx) so it persists
 *   across page navigation — the user can navigate away mid-gather and return to see results.
 */
export { useEvidenceGathering } from '../api/evidenceContext'

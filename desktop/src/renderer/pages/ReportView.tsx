/**
 * @decision DEC-DESKTOP-REPORT-VIEW-001
 * @title ReportView: sandboxed iframe for HTML report rendering
 * @status accepted
 * @rationale The Python backend generates a rich HTML report with markdown rendering
 *   and custom CSS. An iframe with sandbox="allow-same-origin" preserves the report's
 *   own styling while preventing script execution. The iframe's srcdoc attribute is
 *   used (not src) to avoid navigation away from the app. A print button delegates to
 *   the iframe's contentWindow.print() for proper page formatting. The dark overlay
 *   container maintains visual consistency with the app shell.
 *
 * @decision DEC-SECURITY-IFRAME-001
 * @title iframe sandbox: allow-same-origin retained, allow-popups removed
 * @status accepted
 * @rationale Security hardening tightens the iframe sandbox to the minimum required.
 *   allow-popups is removed — reports have no legitimate need to open new browser windows.
 *   allow-same-origin is retained because handlePrint() accesses contentWindow.print()
 *   via the DOM API: without allow-same-origin, srcdoc frames get a null origin and the
 *   cross-origin security model blocks contentWindow access entirely, breaking printing.
 *   allow-scripts is intentionally absent — the report HTML is generated server-side
 *   with no embedded JS, so script execution is never needed.
 */
import { useParams, useNavigate } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { useRef } from 'react'
import { useApiContext } from '../api/context'
import IntelCard from '../components/common/IntelCard'
import ErrorState from '../components/common/ErrorState'

function LoadingState() {
  return (
    <div className="report-loading">
      <div className="skeleton-card skeleton-card-tall" />
    </div>
  )
}

export default function ReportView() {
  const { runId } = useParams<{ runId: string }>()
  const navigate = useNavigate()
  const { baseUrl, client } = useApiContext()
  const iframeRef = useRef<HTMLIFrameElement>(null)

  const {
    data: reportHtml,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['report', runId],
    queryFn: () => client!.getRunReport(runId!, 'html'),
    enabled: !!baseUrl && !!runId,
  })

  

  function handlePrint() {
    if (iframeRef.current?.contentWindow) {
      iframeRef.current.contentWindow.print()
    }
  }

  function handleDownloadReport() {
    if (!client || !runId) return
    client.downloadArtifact(runId, 'report.html').then(blob => {
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `report-${runId}.html`
      a.click()
      URL.revokeObjectURL(url)
    })
  }

  function handleExportAll() {
    if (!client || !runId) return
    client.downloadExport(runId).then(blob => {
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `sat-${runId}.zip`
      a.click()
      URL.revokeObjectURL(url)
    })
  }

  if (isLoading) return <LoadingState />

  if (error) {
    return (
      <ErrorState
        title="Report Unavailable"
        message={`Failed to load report: ${(error as Error).message}`}
        onRetry={() => refetch()}
        onBack={() => navigate(`/runs/${runId}`)}
        backLabel="← Back to Results"
      />
    )
  }

  return (
    <div className="report-view">
      {/* Header toolbar */}
      <div className="report-toolbar">
        <button
          className="btn-back"
          onClick={() => navigate(`/runs/${runId}`)}
        >
          ← Back to Results
        </button>
        <span className="report-toolbar-title">
          Analysis Report — {runId}
        </span>
        {reportHtml && (
          <>
            <button className="btn-print" onClick={handlePrint}>
              Print
            </button>
            <button className="btn-secondary" onClick={handleDownloadReport}>
              Download Report
            </button>
            <button className="btn-secondary" onClick={handleExportAll}>
              Export All
            </button>
          </>
        )}
      </div>

      {/* Report container */}
      {reportHtml ? (
        <div className="report-container">
          <iframe
            ref={iframeRef}
            className="report-iframe"
            sandbox="allow-same-origin"
            title={`Analysis Report — ${runId}`}
            srcDoc={reportHtml}
          />
        </div>
      ) : (
        <IntelCard title="No Report" accent="amber">
          <p className="text-secondary text-sm">
            No HTML report is available for this run. The report may not have been
            generated, or report generation may be disabled.
          </p>
        </IntelCard>
      )}
    </div>
  )
}

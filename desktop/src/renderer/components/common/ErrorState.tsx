/**
 * @file ErrorState.tsx
 * @description Reusable error state component for page-level error display.
 * @rationale Extracted from ReportView's local ErrorState to avoid duplication
 *   across pages. Renders an IntelCard with red accent, an error message, and
 *   optional retry/back buttons. Keeps error presentation consistent across
 *   the app without each page reimplementing the same pattern.
 */
import IntelCard from './IntelCard'

interface ErrorStateProps {
  title?: string
  message: string
  onRetry?: () => void
  onBack?: () => void
  backLabel?: string
}

export default function ErrorState({
  title = 'Something Went Wrong',
  message,
  onRetry,
  onBack,
  backLabel = '← Back',
}: ErrorStateProps) {
  return (
    <IntelCard accent="red" title={title}>
      <p className="text-secondary text-sm">{message}</p>
      <div className="report-error-actions">
        {onBack && (
          <button className="btn-back" onClick={onBack}>
            {backLabel}
          </button>
        )}
        {onRetry && (
          <button className="btn-retry" onClick={onRetry}>
            Retry
          </button>
        )}
      </div>
    </IntelCard>
  )
}

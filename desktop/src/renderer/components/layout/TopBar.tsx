/**
 * @file TopBar.tsx
 * @description Application top bar showing the current page title.
 * @rationale Provides contextual orientation within the app. Falls back to
 *   the product name "Gabo" for unknown routes.
 */
import { useLocation } from 'react-router'
import { useConcurrencyStatus } from '../../hooks/useRuns'

const titles: Record<string, string> = {
  '/': 'Dashboard',
  '/new': 'New Analysis',
  '/about': 'About SAT',
}

export default function TopBar() {
  const location = useLocation()
  const title = titles[location.pathname] ?? 'Gabo'
  const { data: concurrency } = useConcurrencyStatus()

  const activeCount = concurrency ? concurrency.running + concurrency.queued : 0

  return (
    <header className="topbar drag-region">
      <h1 className="topbar-title no-drag">{title}</h1>
      {activeCount > 0 && (
        <div className="topbar-badge no-drag" title={`${concurrency?.running ?? 0} running, ${concurrency?.queued ?? 0} queued`}>
          <span className="topbar-badge-dot" />
          <span className="topbar-badge-text">
            {concurrency?.running ? `${concurrency.running} running` : ''}
            {concurrency?.running && concurrency?.queued ? ' · ' : ''}
            {concurrency?.queued ? `${concurrency.queued} queued` : ''}
          </span>
        </div>
      )}
    </header>
  )
}

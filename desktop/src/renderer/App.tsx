/**
 * @file App.tsx
 * @description Root application shell: sidebar + main content area.
 * @rationale TopBar was removed (page titles are redundant with sidebar active
 *   link highlight). A thin invisible drag strip replaces the TopBar's macOS
 *   traffic-light clearance so the window remains draggable from the main area.
 *
 * @decision DEC-DESKTOP-LAYOUT-001
 * @title TopBar removed; drag strip added to app-main for macOS window dragging
 * @status accepted
 * @rationale The TopBar's page title duplicated information the sidebar's active
 *   link already conveys. Removing it eliminates the sidebar/topbar alignment
 *   mismatch and reclaims vertical space. The concurrency badge moved to the
 *   sidebar footer status area (Sidebar.tsx). A zero-height drag strip preserves
 *   the -webkit-app-region:drag target the TopBar previously provided.
 */
import { Outlet } from 'react-router'
import Sidebar from './components/layout/Sidebar'
import ErrorBoundary from './components/common/ErrorBoundary'

export default function App() {
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="app-main">
        <div className="app-drag-strip drag-region" />
        <main className="app-content">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  )
}

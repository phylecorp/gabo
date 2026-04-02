/**
 * Application entry point - mounts the React tree into #root.
 *
 * Provider nesting order (outermost first):
 *   QueryClientProvider - react-query cache
 *   ApiProvider         - resolves Electron sidecar port, exposes baseUrl/wsBaseUrl
 *   ToastProvider       - global toast notifications
 *   EvidenceGatheringProvider - persistent evidence WS state (survives navigation)
 *   HashRouter          - hash-based routing (required for file:// protocol in packaged app)
 *
 * @decision DEC-ROUTER-001
 * @title Use HashRouter instead of BrowserRouter
 * @status accepted
 * @rationale In production, Electron loads the renderer via loadFile() which creates a
 *   file:// URL. BrowserRouter relies on the HTML5 History API and cannot resolve routes
 *   under file:// — this causes a blank/black screen. HashRouter uses #-based routing
 *   (e.g. file://...index.html#/runs/123) which is URL-origin-agnostic and works correctly
 *   with file:// in packaged builds. In dev mode (HTTP via loadURL) both routers work, so
 *   this change is backward-compatible with development workflow.
 */
import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HashRouter, Routes, Route } from 'react-router'
import App from './App'
import { ApiProvider } from './api/context'
import { ToastProvider } from './components/common/Toast'
import { EvidenceGatheringProvider } from './api/evidenceContext'
import Dashboard from './pages/Dashboard'
import NewAnalysis from './pages/NewAnalysis'
import RunDetail from './pages/RunDetail'
import EvidenceDetail from './pages/EvidenceDetail'
import TechniqueDetail from './pages/TechniqueDetail'
import ReportView from './pages/ReportView'
import Settings from './pages/Settings'
import About from './pages/About'
import './styles/globals.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    }
  }
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ApiProvider>
        <ToastProvider>
          <EvidenceGatheringProvider>
            <HashRouter>
              <Routes>
                <Route element={<App />}>
                  <Route index element={<Dashboard />} />
                  <Route path="new" element={<NewAnalysis />} />
                  <Route path="runs/:runId" element={<RunDetail />} />
                  <Route path="runs/:runId/evidence" element={<EvidenceDetail />} />
                  <Route path="runs/:runId/techniques/:techniqueId" element={<TechniqueDetail />} />
                  <Route path="runs/:runId/report" element={<ReportView />} />
                  <Route path="settings" element={<Settings />} />
                  <Route path="about" element={<About />} />
                </Route>
              </Routes>
            </HashRouter>
          </EvidenceGatheringProvider>
        </ToastProvider>
      </ApiProvider>
    </QueryClientProvider>
  </React.StrictMode>
)

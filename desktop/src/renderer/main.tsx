/**
 * Application entry point - mounts the React tree into #root.
 *
 * Provider nesting order (outermost first):
 *   QueryClientProvider - react-query cache
 *   ApiProvider         - resolves Electron sidecar port, exposes baseUrl/wsBaseUrl
 *   ToastProvider       - global toast notifications
 *   EvidenceGatheringProvider - persistent evidence WS state (survives navigation)
 *   BrowserRouter       - client-side routing
 */
import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Routes, Route } from 'react-router'
import App from './App'
import { ApiProvider } from './api/context'
import { ToastProvider } from './components/common/Toast'
import { EvidenceGatheringProvider } from './api/evidenceContext'
import Dashboard from './pages/Dashboard'
import NewAnalysis from './pages/NewAnalysis'
import RunDetail from './pages/RunDetail'
import TechniqueDetail from './pages/TechniqueDetail'
import ReportView from './pages/ReportView'
import Settings from './pages/Settings'
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
            <BrowserRouter>
              <Routes>
                <Route element={<App />}>
                  <Route index element={<Dashboard />} />
                  <Route path="new" element={<NewAnalysis />} />
                  <Route path="runs/:runId" element={<RunDetail />} />
                  <Route path="runs/:runId/techniques/:techniqueId" element={<TechniqueDetail />} />
                  <Route path="runs/:runId/report" element={<ReportView />} />
                  <Route path="settings" element={<Settings />} />
                </Route>
              </Routes>
            </BrowserRouter>
          </EvidenceGatheringProvider>
        </ToastProvider>
      </ApiProvider>
    </QueryClientProvider>
  </React.StrictMode>
)

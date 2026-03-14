/**
 * @decision DEC-DESKTOP-API-CTX-001
 * @title ApiProvider resolves dynamic Electron port via IPC, falls back to 8742 for dev
 * @status accepted
 * @rationale The sidecar starts on a random port at runtime to avoid conflicts.
 *   The main process exposes the chosen port via IPC (get-api-port). In dev mode
 *   without Electron (e.g. browser-based hot reload), we fall back to the well-known
 *   port 8742 so the dev server can be run separately. Context prevents prop-drilling
 *   the baseUrl down to every hook and component.
 */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

interface ApiContextValue {
  port: number | null
  baseUrl: string | null
  wsBaseUrl: string | null
}

const ApiContext = createContext<ApiContextValue>({ port: null, baseUrl: null, wsBaseUrl: null })

export function ApiProvider({ children }: { children: ReactNode }) {
  const [port, setPort] = useState<number | null>(null)

  useEffect(() => {
    // In dev without Electron, use default port
    if (!window.satAPI) {
      setPort(8742)
      return
    }
    window.satAPI.getApiPort().then((p: number) => setPort(p))
  }, [])

  const baseUrl = port ? `http://127.0.0.1:${port}` : null
  const wsBaseUrl = port ? `ws://127.0.0.1:${port}` : null

  return (
    <ApiContext.Provider value={{ port, baseUrl, wsBaseUrl }}>
      {children}
    </ApiContext.Provider>
  )
}

export function useApiContext() {
  return useContext(ApiContext)
}

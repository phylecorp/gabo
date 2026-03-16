/**
 * @decision DEC-DESKTOP-API-CTX-001
 * @title ApiProvider resolves dynamic Electron port via IPC, falls back to 8742 for dev
 * @status accepted
 * @rationale The sidecar starts on a random port at runtime to avoid conflicts.
 *   The main process exposes the chosen port via IPC (get-api-port). In dev mode
 *   without Electron (e.g. browser-based hot reload), we fall back to the well-known
 *   port 8742 so the dev server can be run separately. Context prevents prop-drilling
 *   the baseUrl down to every hook and component.
 *
 * @decision DEC-AUTH-009
 * @title authToken resolved alongside port via IPC get-auth-token
 * @status accepted
 * @rationale Both port and token are needed before any API call can be made.
 *   Fetching them together in a single useEffect avoids a two-phase render.
 *   The token defaults to empty string in dev mode (no window.satAPI), which
 *   means no Authorization header is sent — this works when the dev server has
 *   SAT_DISABLE_AUTH=1. ApiContextValue exposes authToken so SatClient can be
 *   constructed with it and buildWsUrl() can append ?token= to WebSocket URLs.
 */
import { SatClient } from './client'
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

interface ApiContextValue {
  port: number | null
  baseUrl: string | null
  wsBaseUrl: string | null
  authToken: string
  client: SatClient | null
}

const ApiContext = createContext<ApiContextValue>({
  port: null,
  baseUrl: null,
  wsBaseUrl: null,
  authToken: '',
  client: null,
})

export function ApiProvider({ children }: { children: ReactNode }) {
  const [port, setPort] = useState<number | null>(null)
  const [authToken, setAuthToken] = useState<string>('')

  useEffect(() => {
    // In dev without Electron (browser hot-reload), use default port + no token
    if (!window.satAPI) {
      setPort(8742)
      setAuthToken('')
      return
    }
    // Fetch port and token in parallel — both are needed before API calls
    Promise.all([
      window.satAPI.getApiPort(),
      window.satAPI.getAuthToken(),
    ]).then(([p, token]) => {
      setPort(p)
      setAuthToken(token)
    })
  }, [])

  const baseUrl = port ? `http://127.0.0.1:${port}` : null
  const wsBaseUrl = port ? `ws://127.0.0.1:${port}` : null
  const client = baseUrl ? new SatClient(baseUrl, authToken) : null

  return (
    <ApiContext.Provider value={{ port, baseUrl, wsBaseUrl, authToken, client }}>
      {children}
    </ApiContext.Provider>
  )
}

export function useApiContext() {
  return useContext(ApiContext)
}

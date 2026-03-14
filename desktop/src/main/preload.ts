/**
 * @decision DEC-DESKTOP-PRELOAD-001
 * @title Context bridge exposes only get-api-port via satAPI namespace
 * @status accepted
 * @rationale Minimal surface area on the context bridge reduces attack surface.
 *   The renderer only needs the dynamic port to construct API URLs — all other
 *   communication goes through the HTTP/WS API. contextIsolation + no nodeIntegration
 *   ensures renderer code cannot access Node.js APIs directly.
 *
 * @decision DEC-UPLOAD-001
 * @title openFileDialog added to satAPI context bridge for native file selection
 * @status accepted
 * @rationale The renderer cannot invoke Electron's dialog module directly due to
 *   contextIsolation. IPC is the correct boundary: renderer invokes 'dialog:open-files'
 *   via the context bridge, main process calls dialog.showOpenDialog and returns paths.
 *   This keeps Node.js APIs in the main process only.
 */
import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('satAPI', {
  getApiPort: (): Promise<number> => ipcRenderer.invoke('get-api-port'),
  openFileDialog: (): Promise<string[]> => ipcRenderer.invoke('dialog:open-files'),
})

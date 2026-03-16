/**
 * @decision DEC-DESKTOP-MAIN-001
 * @title Electron main process with sidecar lifecycle management
 * @status accepted
 * @rationale Main process owns the sidecar (Python FastAPI server) lifecycle.
 *   Dev mode skips sidecar when DEV_API_PORT is set, allowing `uvicorn` to run
 *   separately. Dev mode detection uses app.isPackaged (reliable) rather than
 *   NODE_ENV (can be overridden by build tooling).
 *
 * @decision DEC-AUTH-006
 * @title get-auth-token IPC handler exposes token to renderer via context bridge
 * @status accepted
 * @rationale The renderer cannot access Node.js modules directly due to
 *   contextIsolation. IPC is the correct boundary: renderer calls 'get-auth-token'
 *   via window.satAPI.getAuthToken(), main process returns the token captured
 *   from sidecar stdout. In dev mode (DEV_API_PORT set), an empty string is
 *   returned — the frontend falls back to unauthenticated mode which works
 *   when the dev server has SAT_DISABLE_AUTH=1.
 */
import { app, BrowserWindow, ipcMain, dialog } from 'electron'
import { join } from 'path'
import { startSidecar, stopSidecar, getSidecarPort, getSidecarToken } from './sidecar'

const isDev = !app.isPackaged

let mainWindow: BrowserWindow | null = null

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    titleBarStyle: 'hiddenInset',
    backgroundColor: '#0a0a0f',
    icon: join(__dirname, '../../build/icon.png'),
    webPreferences: {
      preload: join(__dirname, '../preload/preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    },
    show: false
  })

  mainWindow.on('ready-to-show', () => {
    mainWindow?.show()
  })

  if (isDev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

app.whenReady().then(async () => {
  // Set dock icon in dev mode (production uses icon.icns via electron-builder)
  if (isDev && process.platform === 'darwin') {
    app.dock.setIcon(join(__dirname, '../../build/icon.png'))
  }

  // Start sidecar (skip in dev if DEV_API_PORT is set)
  const devPort = process.env['DEV_API_PORT']
  if (!devPort) {
    await startSidecar()
  }

  ipcMain.handle('get-api-port', () => {
    return devPort ? parseInt(devPort) : getSidecarPort()
  })

  // Expose auth token to renderer via IPC (DEC-AUTH-006).
  // In dev mode (devPort set), returns empty string — dev server must have
  // SAT_DISABLE_AUTH=1. In production, returns the token from sidecar stdout.
  ipcMain.handle('get-auth-token', () => {
    return devPort ? '' : getSidecarToken()
  })

  ipcMain.handle('dialog:open-files', async () => {
    const result = await dialog.showOpenDialog(mainWindow!, {
      properties: ['openFile', 'multiSelections'],
      filters: [
        { name: 'Documents', extensions: ['pdf', 'docx', 'pptx', 'xlsx', 'html', 'htm', 'txt', 'md', 'csv', 'json'] },
        { name: 'Images', extensions: ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'] },
        { name: 'All Files', extensions: ['*'] },
      ],
    })
    return result.canceled ? [] : result.filePaths
  })

  await createWindow()
})

app.on('window-all-closed', async () => {
  await stopSidecar()
  app.quit()
})

/**
 * @decision DEC-DESKTOP-MAIN-001
 * @title Electron main process with sidecar lifecycle management
 * @status accepted
 * @rationale Main process owns the sidecar (Python FastAPI server) lifecycle.
 *   Dev mode skips sidecar when DEV_API_PORT is set, allowing `uvicorn` to run
 *   separately. Dev mode detection uses app.isPackaged (reliable) rather than
 *   NODE_ENV (can be overridden by build tooling).
 */
import { app, BrowserWindow, ipcMain, dialog } from 'electron'
import { join } from 'path'
import { startSidecar, stopSidecar, getSidecarPort } from './sidecar'

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

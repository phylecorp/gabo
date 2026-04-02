/**
 * @decision DEC-DESKTOP-SIDECAR-001
 * @title Dynamic port allocation + health-poll sidecar startup
 * @status accepted
 * @rationale Finding a free port at startup avoids hardcoded port conflicts on
 *   user machines. Health polling (500ms interval, 30s timeout) is more reliable
 *   than stdout parsing since uvicorn startup messages can vary across versions.
 *   SIGTERM on shutdown is preferred over SIGKILL for graceful FastAPI shutdown.
 *
 * @decision DEC-AUTH-005
 * @title Auth token captured from sidecar stdout before health-poll completes
 * @status accepted
 * @rationale The Python backend prints "SAT_AUTH_TOKEN=<token>" on startup
 *   (before uvicorn begins). Electron captures it by watching stdout data events
 *   before waitForHealth resolves. By the time waitForHealth returns, the token
 *   is guaranteed to be available (the line is printed before uvicorn starts
 *   accepting connections). getSidecarToken() returns the captured token or
 *   empty string if auth is disabled / not yet received.
 *
 * @decision DEC-BUILD-003
 * @title Platform-conditional sidecar path resolution using process.resourcesPath and process.platform
 * @status accepted
 * @rationale When app.isPackaged is true, the PyInstaller binary lives at
 *   <resourcesPath>/sidecar/sat-api/sat-api[.exe]. In dev mode, we spawn
 *   python -m sat.api.main directly. getSidecarPath is a pure function that
 *   accepts (isPackaged, platform, resourcesPath) so it can be unit-tested
 *   without mocking Electron globals. On missing binary in packaged mode, a
 *   user-friendly error dialog is shown before app.quit() to prevent silent
 *   failures on end-user machines.
 */
import { spawn, ChildProcess } from 'child_process'
import * as fs from 'fs'
import * as net from 'net'
import { app, dialog } from 'electron'
import { getSidecarPath } from './sidecar-path'

let sidecarProcess: ChildProcess | null = null
let sidecarPort: number = 0
let sidecarToken: string = ''

async function findFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.listen(0, '127.0.0.1', () => {
      const addr = server.address()
      if (addr && typeof addr === 'object') {
        const port = addr.port
        server.close(() => resolve(port))
      } else {
        reject(new Error('Could not find free port'))
      }
    })
  })
}

async function waitForHealth(port: number, timeoutMs: number = 30000): Promise<void> {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/api/health`)
      if (response.ok) return
    } catch {
      // Server not ready yet
    }
    await new Promise(r => setTimeout(r, 500))
  }
  throw new Error(`Sidecar failed to start within ${timeoutMs}ms`)
}

export async function startSidecar(): Promise<void> {
  sidecarPort = await findFreePort()
  sidecarToken = ''

  const portStr = String(sidecarPort)

  // process.resourcesPath is set by Electron in packaged mode; empty string is
  // safe here because getSidecarPath returns '' when isPackaged is false.
  const resourcesPath = (process as NodeJS.Process & { resourcesPath?: string }).resourcesPath ?? ''
  const sidecarBinaryPath = getSidecarPath({
    isPackaged: app.isPackaged,
    platform: process.platform,
    resourcesPath,
  })

  if (app.isPackaged) {
    // Packaged mode: spawn the PyInstaller binary directly.
    // Check existence first to give a clear error rather than a cryptic spawn failure.
    if (!fs.existsSync(sidecarBinaryPath)) {
      dialog.showErrorBox(
        'SAT Error',
        `Sidecar binary not found at:\n${sidecarBinaryPath}\n\nThe application bundle may be incomplete. Please reinstall.`
      )
      app.quit()
      return
    }

    sidecarProcess = spawn(sidecarBinaryPath, ['--port', portStr], {
      stdio: ['ignore', 'pipe', 'pipe'],
      // Inherit parent environment so API keys (ANTHROPIC_API_KEY, OPENAI_API_KEY,
      // GEMINI_API_KEY, BRAVE_API_KEY, PERPLEXITY_API_KEY, etc.) flow through
      // from the user's system environment. Node spawn inherits env by default
      // but we spread explicitly for clarity and to allow future overrides.
      env: { ...process.env },
    })
  } else {
    // Dev mode: unchanged — spawn python -m sat.api.main
    sidecarProcess = spawn('python', ['-m', 'sat.api.main', '--port', portStr], {
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env }
    })
  }

  sidecarProcess.stdout?.on('data', (data: Buffer) => {
    const text = data.toString()
    // Parse SAT_AUTH_TOKEN=<token> from stdout before uvicorn logs begin
    for (const line of text.split('\n')) {
      const trimmed = line.trim()
      if (trimmed.startsWith('SAT_AUTH_TOKEN=')) {
        sidecarToken = trimmed.slice('SAT_AUTH_TOKEN='.length)
        console.log('[sidecar] auth token received')
      } else if (trimmed) {
        console.log(`[sidecar] ${trimmed}`)
      }
    }
  })

  sidecarProcess.stderr?.on('data', (data: Buffer) => {
    console.error(`[sidecar] ${data.toString().trim()}`)
  })

  sidecarProcess.on('exit', (code) => {
    console.log(`[sidecar] exited with code ${code}`)
    sidecarProcess = null
  })

  await waitForHealth(sidecarPort)
  console.log(`[sidecar] ready on port ${sidecarPort}`)
}

export async function stopSidecar(): Promise<void> {
  if (sidecarProcess) {
    sidecarProcess.kill('SIGTERM')
    sidecarProcess = null
  }
}

export function getSidecarPort(): number {
  return sidecarPort
}

export function getSidecarToken(): string {
  return sidecarToken
}

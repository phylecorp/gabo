/**
 * @decision DEC-DESKTOP-SIDECAR-001
 * @title Dynamic port allocation + health-poll sidecar startup
 * @status accepted
 * @rationale Finding a free port at startup avoids hardcoded port conflicts on
 *   user machines. Health polling (500ms interval, 30s timeout) is more reliable
 *   than stdout parsing since uvicorn startup messages can vary across versions.
 *   SIGTERM on shutdown is preferred over SIGKILL for graceful FastAPI shutdown.
 */
import { spawn, ChildProcess } from 'child_process'
import * as net from 'net'

let sidecarProcess: ChildProcess | null = null
let sidecarPort: number = 0

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

  sidecarProcess = spawn('python', ['-m', 'sat.api.main', '--port', String(sidecarPort)], {
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env }
  })

  sidecarProcess.stdout?.on('data', (data: Buffer) => {
    console.log(`[sidecar] ${data.toString().trim()}`)
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

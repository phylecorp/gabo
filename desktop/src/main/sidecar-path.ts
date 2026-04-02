/**
 * @decision DEC-BUILD-003
 * @title Platform-conditional sidecar path resolution using process.resourcesPath and process.platform
 * @status accepted
 * @rationale getSidecarPath is isolated in this file (no Electron imports) so it
 *   can be unit-tested in a plain Node/vitest environment without mocking the
 *   Electron runtime. sidecar.ts imports from here and passes app.isPackaged +
 *   process.platform + process.resourcesPath as explicit arguments, keeping the
 *   resolution logic pure and the Electron boundary at arm's length.
 */
import * as path from 'path'

/**
 * Resolves the absolute path to the sidecar binary.
 *
 * Pure function — accepts all platform context as explicit arguments so it
 * can be unit-tested without any mocking.
 *
 * @param deps.isPackaged    - Whether the Electron app is packaged (app.isPackaged)
 * @param deps.platform      - OS platform string (process.platform)
 * @param deps.resourcesPath - Electron resources directory (process.resourcesPath)
 * @returns Absolute path to sat-api binary, or '' in dev mode (signals: use python -m)
 */
export function getSidecarPath(deps: {
  isPackaged: boolean
  platform: string
  resourcesPath: string
}): string {
  if (!deps.isPackaged) {
    return ''
  }
  const ext = deps.platform === 'win32' ? '.exe' : ''
  return path.join(deps.resourcesPath, 'sidecar', 'sat-api', 'sat-api' + ext)
}

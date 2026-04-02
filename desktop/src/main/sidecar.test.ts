/**
 * Tests for platform-aware sidecar path resolution (DEC-BUILD-003).
 *
 * getSidecarPath is a pure function that accepts its platform dependencies
 * as parameters (isPackaged, platform, resourcesPath), enabling test-without-mocks.
 *
 * We test getSidecarPath directly with injected values — no mocking of electron
 * or process globals needed.
 *
 * # @mock-exempt: electron app/dialog are Electron runtime APIs unavailable
 * in Node test environment. getSidecarPath is refactored to accept deps as params
 * so all branch logic is tested purely without any mocking.
 */

import { describe, it, expect } from 'vitest'
import { getSidecarPath } from './sidecar-path'

describe('getSidecarPath', () => {
  it('returns empty string in dev mode (isPackaged = false)', () => {
    const result = getSidecarPath({
      isPackaged: false,
      platform: 'darwin',
      resourcesPath: '/Applications/SAT.app/Contents/Resources',
    })
    expect(result).toBe('')
  })

  it('returns macOS binary path (no extension) in packaged mode', () => {
    const result = getSidecarPath({
      isPackaged: true,
      platform: 'darwin',
      resourcesPath: '/Applications/SAT.app/Contents/Resources',
    })
    expect(result).toBe('/Applications/SAT.app/Contents/Resources/sidecar/sat-api/sat-api')
  })

  it('returns Windows binary path (.exe extension) in packaged mode', () => {
    const result = getSidecarPath({
      isPackaged: true,
      platform: 'win32',
      resourcesPath: 'C:\\Program Files\\SAT\\resources',
    })
    // path.join uses the host OS separator — on Windows this produces backslashes,
    // on macOS/Linux it produces forward slashes. We verify the invariants that
    // matter: .exe extension present, correct filename segments, and no double sep.
    expect(result).toContain('sat-api.exe')
    expect(result).toContain('sidecar')
    expect(result).not.toMatch(/\/\/|\\\\/)
  })

  it('returns Linux binary path (no extension) in packaged mode', () => {
    const result = getSidecarPath({
      isPackaged: true,
      platform: 'linux',
      resourcesPath: '/usr/lib/sat/resources',
    })
    expect(result).toBe('/usr/lib/sat/resources/sidecar/sat-api/sat-api')
  })

  it('does not include .exe on macOS even if resourcesPath contains dots', () => {
    const result = getSidecarPath({
      isPackaged: true,
      platform: 'darwin',
      resourcesPath: '/some/path.app/Contents/Resources',
    })
    expect(result).not.toContain('.exe')
  })
})

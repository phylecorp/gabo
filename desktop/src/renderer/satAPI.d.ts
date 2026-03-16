/**
 * Type declarations for the satAPI context bridge exposed by preload.ts.
 *
 * @decision DEC-UPLOAD-002
 * @title Declare satAPI on Window interface for type-safe renderer access
 * @status accepted
 * @rationale The Electron context bridge exposes satAPI as a property on window.
 *   Without a declaration, TypeScript requires `(window as any).satAPI` throughout
 *   the renderer. Adding a proper interface lets callers use window.satAPI directly
 *   with full type checking, and makes the IPC contract explicit.
 *
 * @decision DEC-AUTH-007
 * @title getAuthToken added to SatAPI interface for auth token retrieval
 * @status accepted
 * @rationale The renderer needs the auth token to send Authorization headers.
 *   Declaring it here ensures type-safe access in context.tsx and any component
 *   that directly calls window.satAPI.getAuthToken().
 */

interface SatAPI {
  getApiPort: () => Promise<number>
  getAuthToken: () => Promise<string>
  openFileDialog: () => Promise<string[]>
}

declare global {
  interface Window {
    satAPI?: SatAPI
  }
}

export {}

/**
 * @decision DEC-DESKTOP-RENDERER-REGISTRY-001
 * @title Technique renderer registry: late-binding map from technique_id to component
 * @status accepted
 * @rationale Each technique produces a distinct JSON schema — a single generic table
 *   cannot do justice to ACH matrices, 2x2 scenario grids, or evidence chains. The
 *   registry pattern lets each renderer register itself at import time (side-effect
 *   import) without coupling the registry to a hard-coded list. TechniqueDetail
 *   imports all renderers, triggering registration. Unknown techniques fall back to
 *   a JSON dump rather than crashing.
 */
import type { ComponentType } from 'react'

// Each renderer receives the technique's JSON result as `data` prop
export interface TechniqueRendererProps {
  data: any // The technique-specific result JSON
  techniqueId: string
  techniqueName: string
}

const registry: Record<string, ComponentType<TechniqueRendererProps>> = {}

export function registerRenderer(
  techniqueId: string,
  component: ComponentType<TechniqueRendererProps>
) {
  registry[techniqueId] = component
}

export function getRenderer(
  techniqueId: string
): ComponentType<TechniqueRendererProps> | null {
  return registry[techniqueId] || null
}

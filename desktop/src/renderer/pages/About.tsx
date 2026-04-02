/**
 * @file About.tsx
 * @description Thin page wrapper that renders the Welcome/orientation screen.
 * @rationale The Welcome component is normally shown on Dashboard only when there
 *   are no runs. The About page makes it always reachable via the sidebar so
 *   analysts can revisit onboarding guidance and provider setup instructions
 *   at any time regardless of run history.
 *
 * @decision DEC-DESKTOP-ABOUT-001
 * @title About page wraps Welcome component for persistent reachability
 * @status accepted
 * @rationale Welcome.tsx contains all orientation/setup content. Rather than
 *   duplicating that content, About.tsx is a thin wrapper that reuses it.
 *   hasProviders is derived from useProviders() using the same pattern as
 *   Dashboard.tsx lines 94-95 so the provider status strip remains accurate.
 */
import { useProviders } from '../hooks/useProviders'
import Welcome from '../components/Welcome'

export default function About() {
  const { data: providers } = useProviders()
  const hasProviders = (providers?.filter(p => p.has_api_key) ?? []).length > 0
  return <Welcome hasProviders={hasProviders} />
}

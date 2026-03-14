// Import all technique renderers to trigger registration side-effects.
// TechniqueDetail imports this file; do not tree-shake these imports.

export { default as ACHMatrix } from './ACHMatrix'
export { default as AltFuturesView } from './AltFuturesView'
export { default as AssumptionsView } from './AssumptionsView'
export { default as BrainstormingView } from './BrainstormingView'
export { default as DevilsAdvocacyView } from './DevilsAdvocacyView'
export { default as HighImpactView } from './HighImpactView'
export { default as IndicatorsView } from './IndicatorsView'
export { default as OutsideInView } from './OutsideInView'
export { default as QualityView } from './QualityView'
export { default as RedTeamView } from './RedTeamView'
export { default as TeamABView } from './TeamABView'
export { default as WhatIfView } from './WhatIfView'
export { getRenderer, registerRenderer } from './rendererRegistry'
export type { TechniqueRendererProps } from './rendererRegistry'

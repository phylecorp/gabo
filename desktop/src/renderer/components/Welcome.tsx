/**
 * @decision DEC-DESKTOP-WELCOME-001
 * @title Welcome component: rich onboarding state replacing blank empty state
 * @status accepted
 * @rationale First-time users landing on Dashboard with no runs see a blank
 *   screen with minimal context. This component replaces that empty state with
 *   a structured introduction: what SAT is, what it does well, how to get
 *   started, and what questions it's suited for. This reduces friction for new
 *   analysts and sets accurate expectations about the tool's purpose.
 *   Technique count (12) and provider list (Anthropic, OpenAI, Gemini) are
 *   kept in sync with the backend at time of writing — update if the registry
 *   changes. Navigation links use React Router's Link/useNavigate so they
 *   integrate correctly with SPA routing without page reloads.
 */
import { useNavigate, Link } from 'react-router'

interface WelcomeProps {
  hasProviders: boolean
}

const FEATURE_CARDS = [
  {
    icon: '◈',
    title: '12 Analytic Techniques',
    desc: 'ACH, Key Assumptions Check, Quality of Information Check, Red Team, Devil\'s Advocacy, Team A/B, and more — all automated.',
    accent: 'cyan' as const,
  },
  {
    icon: '⬡',
    title: 'Multi-Model Analysis',
    desc: 'Leverages Anthropic, OpenAI, and Gemini simultaneously for diverse analytical perspectives on the same question.',
    accent: 'green' as const,
  },
  {
    icon: '⚔',
    title: 'Adversarial Critique',
    desc: 'Automated red-team critique with model rebuttal and independent adjudication — structured dissent built into every analysis.',
    accent: 'amber' as const,
  },
  {
    icon: '⊕',
    title: 'Deep Research',
    desc: 'Automated evidence gathering from Perplexity, Brave, and other research providers before analysis begins.',
    accent: 'purple' as const,
  },
]

const STEPS = [
  {
    n: 1,
    text: (
      <>
        Configure API keys in{' '}
        <Link to="/settings" className="welcome-link">Settings</Link>
        {' '}(Anthropic, OpenAI, and/or Gemini)
      </>
    ),
  },
  { n: 2, text: 'Start a new analysis — provide your intelligence question and optional source material' },
  { n: 3, text: 'Review gathered evidence and select which items the pipeline should reason over' },
  { n: 4, text: 'Run the analysis pipeline and review technique-by-technique results and the executive synthesis' },
]

export default function Welcome({ hasProviders }: WelcomeProps) {
  const navigate = useNavigate()

  return (
    <div className="welcome">
      {/* Header */}
      <div className="welcome-header">
        <div className="welcome-logo-mark">◎</div>
        <h1 className="welcome-title">Structured Analytic Techniques</h1>
        <p className="welcome-subtitle text-secondary">
          CIA Tradecraft Primer Analysis Pipeline
        </p>
      </div>

      {!hasProviders && (
        <div className="welcome-provider-warn">
          <span className="welcome-warn-icon">⚠</span>
          <span>
            No LLM provider API keys configured.{' '}
            <Link to="/settings" className="welcome-link">Configure keys</Link>
            {' '}to enable analysis.
          </span>
        </div>
      )}

      {/* What SAT Does */}
      <section className="welcome-section">
        <h2 className="welcome-section-title">What SAT Does</h2>
        <div className="welcome-features-grid">
          {FEATURE_CARDS.map(card => (
            <div key={card.title} className={`welcome-feature-card welcome-feature-card-${card.accent}`}>
              <div className={`welcome-feature-icon welcome-feature-icon-${card.accent}`}>{card.icon}</div>
              <div className="welcome-feature-body">
                <div className="welcome-feature-title">{card.title}</div>
                <p className="welcome-feature-desc text-secondary text-sm">{card.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* How to Get Started */}
      <section className="welcome-section">
        <h2 className="welcome-section-title">How to Get Started</h2>
        <ol className="welcome-steps">
          {STEPS.map(step => (
            <li key={step.n} className="welcome-step">
              <span className="welcome-step-num">{step.n}</span>
              <span className="welcome-step-text text-secondary">{step.text}</span>
            </li>
          ))}
        </ol>
      </section>

      {/* Good At / Not Ideal For */}
      <section className="welcome-section welcome-fit-section">
        <div className="welcome-fit-grid">
          <div className="welcome-fit-card welcome-fit-good">
            <h3 className="welcome-fit-heading">SAT Is Good At</h3>
            <ul className="welcome-fit-list">
              <li>Structured analysis of complex geopolitical and intelligence questions</li>
              <li>Multi-perspective assessment of ambiguous situations</li>
              <li>Evidence-based reasoning with explicit assumption tracking</li>
              <li>Surfacing analytic biases and alternative hypotheses</li>
              <li>Generating structured dissent through adversarial critique</li>
            </ul>
          </div>
          <div className="welcome-fit-card welcome-fit-caution">
            <h3 className="welcome-fit-heading">Not Ideal For</h3>
            <ul className="welcome-fit-list">
              <li>Real-time monitoring or live data feeds</li>
              <li>Simple factual lookups with clear single answers</li>
              <li>Questions requiring classified or proprietary data</li>
              <li>Rapid turnaround with no evidence review step</li>
            </ul>
          </div>
        </div>
      </section>

      {/* CTA */}
      <div className="welcome-cta">
        <button
          className="btn-primary btn-lg"
          onClick={() => navigate('/new')}
        >
          Start Your First Analysis
        </button>
        {!hasProviders && (
          <Link to="/settings" className="btn-secondary welcome-cta-secondary">
            Configure API Keys
          </Link>
        )}
      </div>
    </div>
  )
}

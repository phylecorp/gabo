/**
 * @file ErrorBoundary.tsx
 * @description React error boundary that catches unhandled render errors and shows a recovery UI.
 * @rationale Class components are required for componentDidCatch/getDerivedStateFromError —
 *   there is no hooks equivalent. The functional wrapper reads useNavigate so the reset
 *   action can navigate to the dashboard, which is a React-Router concern that belongs
 *   outside the class. This split (inner class + outer functional wrapper) is the
 *   canonical pattern for error boundaries in React Router v6 apps.
 *
 * @decision DEC-DESKTOP-ERROR-BOUNDARY-001
 * @title ErrorBoundary: class component inner + functional wrapper for router integration
 * @status accepted
 * @rationale getDerivedStateFromError requires a class component. useNavigate requires
 *   a functional component. The wrapper pattern satisfies both constraints cleanly
 *   without introducing a third-party library.
 */
import { Component, type ReactNode } from 'react'
import { useNavigate } from 'react-router'
import IntelCard from './IntelCard'

interface Props {
  children: ReactNode
  onReset?: () => void
}

interface State {
  hasError: boolean
  error: Error | null
}

class ErrorBoundaryInner extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary-screen">
          <IntelCard accent="red" title="Something Went Wrong">
            <p className="text-secondary text-sm">
              An unexpected error occurred in this page.
            </p>
            {this.state.error && (
              <pre className="error-boundary-detail">{this.state.error.message}</pre>
            )}
            <div className="report-error-actions">
              <button
                className="btn-back"
                onClick={() => {
                  this.setState({ hasError: false, error: null })
                  this.props.onReset?.()
                }}
              >
                Return to Dashboard
              </button>
            </div>
          </IntelCard>
        </div>
      )
    }
    return this.props.children
  }
}

export default function ErrorBoundary({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  return (
    <ErrorBoundaryInner onReset={() => navigate('/')}>
      {children}
    </ErrorBoundaryInner>
  )
}

/**
 * @file Toast.tsx
 * @description Context-based toast notification system for transient user feedback.
 * @rationale Toast notifications let pages surface ephemeral errors (delete failures,
 *   network issues) without blocking the UI or requiring navigation. A context-based
 *   design means any component can call addToast without prop drilling. Max 3 visible
 *   toasts prevents visual overload; 5s auto-dismiss keeps notifications from
 *   accumulating. Timeout cleanup on unmount prevents memory leaks.
 *
 * @decision DEC-DESKTOP-TOAST-001
 * @title Toast: context-based notification system with auto-dismiss and max-3 cap
 * @status accepted
 * @rationale Context avoids prop drilling for ephemeral notifications. Auto-dismiss
 *   at 5s and a cap of 3 visible toasts prevents notification overload. useRef for
 *   timer tracking ensures cleanup on unmount without re-render side effects.
 */
import { createContext, useContext, useRef, useState, useCallback, useEffect, type ReactNode } from 'react'

type ToastVariant = 'error' | 'warning' | 'info' | 'success'

interface Toast {
  id: number
  message: string
  variant: ToastVariant
}

interface ToastContextValue {
  addToast: (message: string, variant?: ToastVariant) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within a ToastProvider')
  return ctx
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(0)
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map())

  // Cleanup all timers on unmount
  useEffect(() => {
    const t = timers.current
    return () => { t.forEach(timer => clearTimeout(timer)) }
  }, [])

  const addToast = useCallback((message: string, variant: ToastVariant = 'info') => {
    const id = nextId.current++
    setToasts(prev => {
      const next = [...prev, { id, message, variant }]
      return next.slice(-3) // keep last 3
    })

    const timer = setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
      timers.current.delete(id)
    }, 5000)
    timers.current.set(id, timer)
  }, [])

  function dismiss(id: number) {
    const timer = timers.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timers.current.delete(id)
    }
    setToasts(prev => prev.filter(t => t.id !== id))
  }

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <div className="toast-stack">
        {toasts.map(toast => (
          <div key={toast.id} className={`toast toast-${toast.variant}`}>
            <span className="toast-message">{toast.message}</span>
            <button
              className="toast-dismiss"
              onClick={() => dismiss(toast.id)}
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

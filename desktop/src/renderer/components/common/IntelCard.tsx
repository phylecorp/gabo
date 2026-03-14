import type { ReactNode } from 'react'

interface IntelCardProps {
  title?: string
  subtitle?: string
  children: ReactNode
  className?: string
  variant?: 'default' | 'elevated'
  accent?: 'cyan' | 'green' | 'amber' | 'red' | 'purple'
}

export default function IntelCard({ title, subtitle, children, className = '', variant = 'default', accent }: IntelCardProps) {
  return (
    <div className={`intel-card intel-card-${variant} ${accent ? `intel-card-accent-${accent}` : ''} ${className}`}>
      {(title || subtitle) && (
        <div className="intel-card-header">
          {title && <h3 className="intel-card-title">{title}</h3>}
          {subtitle && <span className="intel-card-subtitle">{subtitle}</span>}
        </div>
      )}
      <div className="intel-card-body">
        {children}
      </div>
    </div>
  )
}

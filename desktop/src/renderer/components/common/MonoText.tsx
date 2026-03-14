import type { ReactNode } from 'react'

interface MonoTextProps {
  children: ReactNode
  size?: 'xs' | 'sm' | 'base'
  color?: 'primary' | 'secondary' | 'muted' | 'cyan' | 'green' | 'amber'
  className?: string
}

export default function MonoText({ children, size = 'sm', color = 'secondary', className = '' }: MonoTextProps) {
  return (
    <span className={`font-mono text-${size} mono-${color} ${className}`}>
      {children}
    </span>
  )
}

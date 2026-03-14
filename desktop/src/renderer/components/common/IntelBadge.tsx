interface IntelBadgeProps {
  label: string
  variant?: 'default' | 'confidence' | 'severity' | 'category' | 'provider'
  level?: 'high' | 'medium' | 'low' | 'critical'
  category?: 'diagnostic' | 'contrarian' | 'imaginative'
}

export default function IntelBadge({ label, variant = 'default', level, category }: IntelBadgeProps) {
  let colorClass = 'badge-default'

  if (variant === 'confidence' || variant === 'severity') {
    colorClass = level === 'high' || level === 'critical' ? 'badge-red'
      : level === 'medium' ? 'badge-amber'
      : 'badge-green'
  } else if (variant === 'category') {
    colorClass = category === 'diagnostic' ? 'badge-green'
      : category === 'contrarian' ? 'badge-amber'
      : 'badge-purple'
  }

  return <span className={`intel-badge ${colorClass}`}>{label}</span>
}

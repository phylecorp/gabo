interface IntelProgressProps {
  value: number
  max?: number
  label?: string
  variant?: 'cyan' | 'green' | 'amber' | 'red'
}

export default function IntelProgress({ value, max = 100, label, variant = 'cyan' }: IntelProgressProps) {
  const pct = Math.min(100, (value / max) * 100)
  return (
    <div className="intel-progress">
      {label && <span className="intel-progress-label">{label}</span>}
      <div className="intel-progress-track">
        <div
          className={`intel-progress-fill progress-${variant}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

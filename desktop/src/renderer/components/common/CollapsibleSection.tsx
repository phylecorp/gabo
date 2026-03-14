import { useState, type ReactNode } from 'react'

interface CollapsibleSectionProps {
  title: string
  children: ReactNode
  defaultOpen?: boolean
  count?: number
}

export default function CollapsibleSection({ title, children, defaultOpen = true, count }: CollapsibleSectionProps) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className="collapsible">
      <button className="collapsible-trigger" onClick={() => setOpen(!open)}>
        <span className={`collapsible-arrow ${open ? 'open' : ''}`}>▸</span>
        <span className="collapsible-title">{title}</span>
        {count !== undefined && <span className="collapsible-count">{count}</span>}
      </button>
      {open && <div className="collapsible-content">{children}</div>}
    </div>
  )
}

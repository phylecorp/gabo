/**
 * @file Sidebar.tsx
 * @description Application sidebar with primary navigation links and Settings entry.
 * @rationale Sidebar is the persistent navigation anchor. Settings is placed at the
 *   bottom of the footer (above the status strip) so it is accessible but not
 *   competing with the primary workflow actions (Dashboard, New Analysis).
 *
 * @decision DEC-DESKTOP-SIDEBAR-001
 * @title Settings nav item placed in footer, not main nav list
 * @status accepted
 * @rationale Settings is a low-frequency action (configure once, rarely revisit).
 *   Placing it in the footer keeps the primary nav focused on workflow actions.
 *   Using NavLink with isActive gives it the same active highlight as other items.
 */
import { NavLink } from 'react-router'

const navItems = [
  { to: '/', label: 'Dashboard', icon: '◉' },
  { to: '/new', label: 'New Analysis', icon: '⊕' },
]

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-header drag-region">
        <div className="sidebar-logo-row">
          <svg className="sidebar-logo-icon" width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
            {/* Square sunglasses: temple arms, left lens, nose bridge, right lens */}
            {/* Left temple arm */}
            <rect x="0" y="10" width="2" height="1.5" rx="0.5"/>
            {/* Left lens */}
            <rect x="2" y="9" width="8" height="6" rx="1"/>
            {/* Nose bridge */}
            <rect x="10" y="11" width="4" height="1.5" rx="0.5"/>
            {/* Right lens */}
            <rect x="14" y="9" width="8" height="6" rx="1"/>
            {/* Right temple arm */}
            <rect x="22" y="10" width="2" height="1.5" rx="0.5"/>
          </svg>
          <span className="sidebar-logo">Gabo</span>
        </div>
      </div>
      <nav className="sidebar-nav">
        {navItems.map(item => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              `sidebar-link ${isActive ? 'sidebar-link-active' : ''}`
            }
          >
            <span className="sidebar-icon">{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-footer">
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            `sidebar-link ${isActive ? 'sidebar-link-active' : ''}`
          }
          style={{ marginBottom: '8px' }}
        >
          <span className="sidebar-icon">⚙</span>
          Settings
        </NavLink>
        <div className="sidebar-status">
          <span className="status-dot status-dot-ok" />
          <span className="text-secondary text-xs">System Ready</span>
        </div>
      </div>
    </aside>
  )
}

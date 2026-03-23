import { NavLink } from 'react-router-dom'

const NAV_ITEMS = [
  { to: '/', label: 'Datasets', icon: DatasetIcon },
  { to: '/training', label: 'Training', icon: TrainingIcon },
  { to: '/models', label: 'Models', icon: ModelsIcon },
  { to: '/arena', label: 'Arena', icon: ArenaIcon },
  { to: '/leaderboard', label: 'Leaderboard', icon: LeaderboardIcon },
]

export default function Sidebar() {
  return (
    <aside className="w-56 shrink-0 bg-bg-secondary border-r border-border-default flex flex-col h-screen sticky top-0">
      <div className="px-5 py-5 border-b border-border-default">
        <h1 className="text-lg font-semibold tracking-tight text-text-primary font-mono m-0">
          <span className="text-accent-success">Synth</span>Board
        </h1>
        <p className="text-xs text-text-muted mt-0.5">Local Fine-Tuning Arena</p>
      </div>

      <nav className="flex-1 py-3 px-3 flex flex-col gap-0.5">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-bg-hover text-accent-success'
                  : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary'
              }`
            }
          >
            <Icon />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="px-4 py-3 border-t border-border-default">
        <p className="text-xs text-text-muted">RTX 3050 · 6 GB VRAM</p>
      </div>
    </aside>
  )
}

function DatasetIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="2" width="12" height="12" rx="2" />
      <line x1="2" y1="6" x2="14" y2="6" />
      <line x1="2" y1="10" x2="14" y2="10" />
      <line x1="6" y1="6" x2="6" y2="14" />
    </svg>
  )
}

function TrainingIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="2,12 5,6 8,9 11,3 14,7" />
    </svg>
  )
}

function ModelsIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="1" width="10" height="14" rx="2" />
      <line x1="6" y1="5" x2="10" y2="5" />
      <line x1="6" y1="8" x2="10" y2="8" />
      <line x1="6" y1="11" x2="8" y2="11" />
    </svg>
  )
}

function ArenaIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4,2 L4,8 Q4,12 8,13 Q12,12 12,8 L12,2" />
      <line x1="4" y1="6" x2="12" y2="6" />
    </svg>
  )
}

function LeaderboardIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="1" y="8" width="4" height="6" />
      <rect x="6" y="3" width="4" height="11" />
      <rect x="11" y="6" width="4" height="8" />
    </svg>
  )
}

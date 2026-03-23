import { useLocation } from 'react-router-dom'
import useGpuStats from '../../hooks/useGpuStats'

const PAGE_TITLES = {
  '/': 'Datasets',
  '/training': 'Training',
  '/models': 'Models',
  '/arena': 'Arena',
  '/leaderboard': 'Leaderboard',
}

function getVramColor(pct) {
  if (pct >= 85) return 'var(--color-accent-error)'
  if (pct >= 60) return 'var(--color-accent-warning)'
  return 'var(--color-accent-success)'
}

export default function TopBar() {
  const { pathname } = useLocation()
  const title = PAGE_TITLES[pathname] || 'SynthBoard'
  const { stats, error } = useGpuStats(5000)

  const available = stats?.available
  const usedMb = stats?.vram_used_mb ?? 0
  const totalMb = stats?.vram_total_mb ?? 1
  const pct = Math.round((usedMb / totalMb) * 100)
  const usedGb = (usedMb / 1024).toFixed(1)
  const totalGb = (totalMb / 1024).toFixed(1)
  const temp = stats?.temperature_c
  const gpuName = stats?.name

  return (
    <header className="h-14 shrink-0 bg-bg-secondary border-b border-border-default flex items-center justify-between px-6">
      <h2 className="text-sm font-semibold text-text-primary tracking-wide uppercase m-0">
        {title}
      </h2>

      <div className="flex items-center gap-4">
        {/* GPU name + temp */}
        {available && gpuName && (
          <span className="text-xs text-text-muted hidden lg:inline">
            {gpuName}
            {temp != null && (
              <span className="font-mono ml-1.5" style={{ color: temp >= 80 ? 'var(--color-accent-error)' : 'var(--color-text-secondary)' }}>
                {temp}°C
              </span>
            )}
          </span>
        )}

        {/* VRAM bar */}
        <div className="flex items-center gap-2.5">
          <span className="text-xs text-text-muted font-mono">VRAM</span>
          <div className="w-28 h-2.5 bg-bg-primary rounded-full overflow-hidden border border-border-default">
            {available ? (
              <div
                className="h-full rounded-full transition-all duration-700 ease-out"
                style={{ width: `${pct}%`, backgroundColor: getVramColor(pct) }}
              />
            ) : (
              <div className="h-full w-full bg-border-default animate-pulse" />
            )}
          </div>
          <span className="text-xs font-mono text-text-secondary min-w-[5.5rem] text-right">
            {error ? (
              <span className="text-accent-error">offline</span>
            ) : available ? (
              `${usedGb} / ${totalGb} GB`
            ) : (
              '— / — GB'
            )}
          </span>
        </div>
      </div>
    </header>
  )
}

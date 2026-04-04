/**
 * Skeleton loading placeholders — pulsing bars that match the dark theme.
 */

export function SkeletonLine({ className = '' }) {
  return (
    <div className={`h-3 bg-bg-hover rounded animate-pulse ${className}`} />
  )
}

export function SkeletonBlock({ className = '' }) {
  return (
    <div className={`bg-bg-hover rounded-lg animate-pulse ${className}`} />
  )
}

/** Generic card skeleton with a few lines */
export function SkeletonCard() {
  return (
    <div className="bg-bg-secondary border border-border-default rounded-lg p-4 space-y-3">
      <div className="flex items-center gap-3">
        <SkeletonBlock className="w-8 h-8 rounded" />
        <SkeletonLine className="flex-1 max-w-[200px]" />
      </div>
      <SkeletonLine className="w-3/4" />
      <SkeletonLine className="w-1/2" />
    </div>
  )
}

/** Table row skeleton */
export function SkeletonRow({ cols = 5 }) {
  return (
    <tr className="border-t border-border-default">
      {Array.from({ length: cols }, (_, i) => (
        <td key={i} className="px-4 py-3">
          <SkeletonLine className={i === 0 ? 'w-32' : 'w-16'} />
        </td>
      ))}
    </tr>
  )
}

/** Table skeleton with header + N rows */
export function SkeletonTable({ rows = 4, cols = 5 }) {
  return (
    <div className="border border-border-default rounded-lg overflow-hidden">
      <div className="bg-bg-tertiary px-4 py-2.5">
        <SkeletonLine className="w-48 h-2.5" />
      </div>
      <table className="w-full">
        <tbody>
          {Array.from({ length: rows }, (_, i) => (
            <SkeletonRow key={i} cols={cols} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** List item skeleton */
export function SkeletonListItem() {
  return (
    <div className="px-4 py-3 border-b border-border-subtle">
      <SkeletonLine className="w-40 mb-2" />
      <div className="flex gap-2">
        <SkeletonLine className="w-12" />
        <SkeletonLine className="w-16" />
        <SkeletonLine className="w-14" />
      </div>
    </div>
  )
}

/** Stat card skeleton (for leaderboard) */
export function SkeletonStatCard() {
  return (
    <div className="bg-bg-secondary border border-border-default rounded-lg px-4 py-3 space-y-2">
      <SkeletonLine className="w-16 h-2" />
      <SkeletonLine className="w-24 h-5" />
    </div>
  )
}

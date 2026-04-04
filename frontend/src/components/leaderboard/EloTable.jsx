import { useState, useMemo } from 'react'
import { LineChart, Line, ResponsiveContainer } from 'recharts'

const SOURCE_BADGES = {
  base: { label: 'Base', bg: 'bg-accent-info/15', text: 'text-accent-info' },
  'fine-tuned': { label: 'Fine-tuned', bg: 'bg-accent-success/15', text: 'text-accent-success' },
}

const COLUMNS = [
  { key: 'rank', label: '#', sortable: false, align: 'center', width: 'w-12' },
  { key: 'name', label: 'Model', sortable: true, align: 'left', width: 'flex-1' },
  { key: 'source', label: 'Source', sortable: true, align: 'center', width: 'w-24' },
  { key: 'elo_rating', label: 'Elo Rating', sortable: true, align: 'right', width: 'w-40' },
  { key: 'win_rate', label: 'Win %', sortable: true, align: 'right', width: 'w-20' },
  { key: 'total_battles', label: 'Battles', sortable: true, align: 'right', width: 'w-20' },
  { key: 'record', label: 'W/L/T', sortable: false, align: 'center', width: 'w-28' },
  { key: 'avg_ttft_ms', label: 'TTFT', sortable: true, align: 'right', width: 'w-20' },
  { key: 'avg_tps', label: 'TPS', sortable: true, align: 'right', width: 'w-20' },
]

function EloSparkline({ history }) {
  if (!history || history.length < 2) return null
  return (
    <div className="inline-block w-16 h-5 ml-2 align-middle">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={history}>
          <Line
            type="monotone"
            dataKey="elo_rating"
            stroke="var(--color-accent-success)"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function EloTable({ models, eloHistories, expandedId, onExpand }) {
  const [sortKey, setSortKey] = useState('elo_rating')
  const [sortDir, setSortDir] = useState('desc')

  const handleSort = (key) => {
    if (!COLUMNS.find(c => c.key === key)?.sortable) return
    if (sortKey === key) {
      setSortDir(d => d === 'desc' ? 'asc' : 'desc')
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  const sorted = useMemo(() => {
    if (!models?.length) return []
    const arr = [...models]
    arr.sort((a, b) => {
      let va = a[sortKey]
      let vb = b[sortKey]
      if (va == null) va = -Infinity
      if (vb == null) vb = -Infinity
      if (typeof va === 'string') {
        const cmp = va.localeCompare(vb)
        return sortDir === 'asc' ? cmp : -cmp
      }
      return sortDir === 'asc' ? va - vb : vb - va
    })
    return arr.map((m, i) => ({ ...m, rank: i + 1 }))
  }, [models, sortKey, sortDir])

  if (!models?.length) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <svg className="w-12 h-12 mb-4 text-text-muted opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 18.75h-9m9 0a3 3 0 0 1 3 3h-15a3 3 0 0 1 3-3m9 0v-4.5A3.375 3.375 0 0 0 13.125 10.875h-2.25A3.375 3.375 0 0 0 7.5 14.25v4.5m9-9V3.75m-9 5.25V3.75m9 0h-9m9 0a1.5 1.5 0 0 1 1.5 1.5v1.5m-12-3a1.5 1.5 0 0 0-1.5 1.5v1.5" />
        </svg>
        <p className="text-sm text-text-muted mb-1">No models in the arena yet</p>
        <p className="text-xs text-text-muted">Register base models or export fine-tuned models to see rankings.</p>
      </div>
    )
  }

  return (
    <div className="bg-bg-secondary border border-border-default rounded-lg overflow-hidden">
      {/* Header row */}
      <div className="flex items-center gap-0 px-4 py-2.5 border-b border-border-default bg-bg-tertiary text-[10px] uppercase tracking-wider text-text-muted font-semibold select-none">
        {COLUMNS.map(col => (
          <div
            key={col.key}
            className={`${col.width} shrink-0 ${col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left'} ${col.sortable ? 'cursor-pointer hover:text-text-secondary transition-colors' : ''}`}
            onClick={() => handleSort(col.key)}
          >
            {col.label}
            {col.sortable && sortKey === col.key && (
              <span className="ml-0.5 text-accent-success">{sortDir === 'desc' ? ' \u25BE' : ' \u25B4'}</span>
            )}
          </div>
        ))}
      </div>

      {/* Rows */}
      {sorted.map(model => {
        const isExpanded = expandedId === model.id
        const history = eloHistories[model.id]
        const eloColor = model.elo_rating >= 1200 ? 'text-accent-success' : 'text-accent-error'

        return (
          <div key={model.id}>
            <div
              className={`flex items-center gap-0 px-4 py-3 border-b border-border-default cursor-pointer transition-colors ${
                isExpanded ? 'bg-bg-hover' : 'hover:bg-bg-hover/50'
              }`}
              onClick={() => onExpand(isExpanded ? null : model.id)}
            >
              {/* Rank */}
              <div className="w-12 shrink-0 text-center">
                <span className={`font-mono text-sm font-bold ${
                  model.rank === 1 ? 'text-accent-warning' : model.rank === 2 ? 'text-text-secondary' : model.rank === 3 ? 'text-amber-600' : 'text-text-muted'
                }`}>
                  {model.rank}
                </span>
              </div>

              {/* Name */}
              <div className="flex-1 shrink-0 min-w-0">
                <span className="text-sm font-medium text-text-primary truncate block">{model.name}</span>
              </div>

              {/* Source */}
              <div className="w-24 shrink-0 text-center">
                <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${(SOURCE_BADGES[model.source] || SOURCE_BADGES.base).bg} ${(SOURCE_BADGES[model.source] || SOURCE_BADGES.base).text}`}>
                  {(SOURCE_BADGES[model.source] || SOURCE_BADGES.base).label}
                </span>
              </div>

              {/* Elo + sparkline */}
              <div className="w-40 shrink-0 text-right flex items-center justify-end">
                <span className={`font-mono text-sm font-bold ${eloColor}`}>
                  {model.elo_rating.toFixed(1)}
                </span>
                <EloSparkline history={history} />
              </div>

              {/* Win % */}
              <div className="w-20 shrink-0 text-right">
                <span className="font-mono text-sm text-text-secondary">
                  {model.total_battles > 0 ? `${model.win_rate.toFixed(0)}%` : '--'}
                </span>
              </div>

              {/* Battles */}
              <div className="w-20 shrink-0 text-right">
                <span className="font-mono text-sm text-text-secondary">{model.total_battles}</span>
              </div>

              {/* W/L/T */}
              <div className="w-28 shrink-0 text-center">
                <span className="font-mono text-xs">
                  <span className="text-accent-success">{model.total_wins}</span>
                  <span className="text-text-muted">/</span>
                  <span className="text-accent-error">{model.total_losses}</span>
                  <span className="text-text-muted">/</span>
                  <span className="text-text-muted">{model.total_ties}</span>
                </span>
              </div>

              {/* TTFT */}
              <div className="w-20 shrink-0 text-right">
                <span className="font-mono text-sm text-text-secondary">
                  {model.avg_ttft_ms != null ? `${model.avg_ttft_ms.toFixed(0)}` : '--'}
                </span>
              </div>

              {/* TPS */}
              <div className="w-20 shrink-0 text-right">
                <span className="font-mono text-sm text-text-secondary">
                  {model.avg_tps != null ? `${model.avg_tps.toFixed(1)}` : '--'}
                </span>
              </div>
            </div>

            {/* Expand indicator */}
            {isExpanded && (
              <div className="border-b border-accent-success/20 h-0.5 bg-accent-success/10" />
            )}
          </div>
        )
      })}
    </div>
  )
}

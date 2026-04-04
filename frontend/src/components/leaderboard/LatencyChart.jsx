import { BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

export default function LatencyChart({ model, allModels }) {
  // Build comparison data: show this model vs all others
  const ttftData = allModels
    .filter(m => m.avg_ttft_ms != null)
    .map(m => ({
      name: m.name.length > 12 ? m.name.slice(0, 12) + '...' : m.name,
      value: m.avg_ttft_ms,
      fill: m.id === model.id ? 'var(--color-accent-info)' : 'var(--color-border-default)',
    }))

  const tpsData = allModels
    .filter(m => m.avg_tps != null)
    .map(m => ({
      name: m.name.length > 12 ? m.name.slice(0, 12) + '...' : m.name,
      value: m.avg_tps,
      fill: m.id === model.id ? 'var(--color-accent-success)' : 'var(--color-border-default)',
    }))

  const hasData = ttftData.length > 0 || tpsData.length > 0

  if (!hasData) {
    return (
      <div className="h-full flex items-center justify-center text-xs text-text-muted">
        No latency data yet
      </div>
    )
  }

  const tooltipStyle = {
    backgroundColor: 'var(--color-bg-secondary)',
    border: '1px solid var(--color-border-default)',
    borderRadius: '6px',
    fontSize: 12,
    fontFamily: 'var(--font-mono)',
  }

  return (
    <div className="grid grid-cols-2 gap-6">
      {/* TTFT chart */}
      <div>
        <div className="text-[10px] text-text-muted uppercase tracking-wider mb-2">
          Avg Time to First Token (ms)
        </div>
        {ttftData.length > 0 ? (
          <ResponsiveContainer width="100%" height={120}>
            <BarChart data={ttftData} layout="vertical" margin={{ left: 0, right: 10, top: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-default)" horizontal={false} />
              <XAxis
                type="number"
                stroke="var(--color-text-muted)"
                tick={{ fontSize: 10, fontFamily: 'var(--font-mono)' }}
              />
              <YAxis
                type="category"
                dataKey="name"
                width={90}
                stroke="var(--color-text-muted)"
                tick={{ fontSize: 10, fontFamily: 'var(--font-mono)' }}
              />
              <Tooltip
                contentStyle={tooltipStyle}
                formatter={(v) => [`${v.toFixed(0)} ms`, 'TTFT']}
              />
              <Bar dataKey="value" radius={[0, 3, 3, 0]} isAnimationActive={false}>
                {ttftData.map((entry, i) => (
                  <Cell key={i} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-[120px] flex items-center justify-center text-xs text-text-muted">No data</div>
        )}
      </div>

      {/* TPS chart */}
      <div>
        <div className="text-[10px] text-text-muted uppercase tracking-wider mb-2">
          Avg Tokens per Second
        </div>
        {tpsData.length > 0 ? (
          <ResponsiveContainer width="100%" height={120}>
            <BarChart data={tpsData} layout="vertical" margin={{ left: 0, right: 10, top: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-default)" horizontal={false} />
              <XAxis
                type="number"
                stroke="var(--color-text-muted)"
                tick={{ fontSize: 10, fontFamily: 'var(--font-mono)' }}
              />
              <YAxis
                type="category"
                dataKey="name"
                width={90}
                stroke="var(--color-text-muted)"
                tick={{ fontSize: 10, fontFamily: 'var(--font-mono)' }}
              />
              <Tooltip
                contentStyle={tooltipStyle}
                formatter={(v) => [`${v.toFixed(1)} tok/s`, 'TPS']}
              />
              <Bar dataKey="value" radius={[0, 3, 3, 0]} isAnimationActive={false}>
                {tpsData.map((entry, i) => (
                  <Cell key={i} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-[120px] flex items-center justify-center text-xs text-text-muted">No data</div>
        )}
      </div>
    </div>
  )
}

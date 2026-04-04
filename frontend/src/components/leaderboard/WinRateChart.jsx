import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'

const COLORS = {
  wins: 'var(--color-accent-success)',
  losses: 'var(--color-accent-error)',
  ties: 'var(--color-accent-warning)',
}

export default function WinRateChart({ model }) {
  const data = [
    { name: 'Wins', value: model.total_wins, color: COLORS.wins },
    { name: 'Losses', value: model.total_losses, color: COLORS.losses },
    { name: 'Ties', value: model.total_ties, color: COLORS.ties },
  ].filter(d => d.value > 0)

  if (data.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-xs text-text-muted">
        No battles yet
      </div>
    )
  }

  const total = model.total_wins + model.total_losses + model.total_ties

  return (
    <div className="flex items-center gap-4">
      <div className="w-32 h-32">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={30}
              outerRadius={55}
              paddingAngle={2}
              dataKey="value"
              isAnimationActive={false}
            >
              {data.map((entry, i) => (
                <Cell key={i} fill={entry.color} stroke="none" />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                backgroundColor: 'var(--color-bg-secondary)',
                border: '1px solid var(--color-border-default)',
                borderRadius: '6px',
                fontSize: 12,
                fontFamily: 'var(--font-mono)',
              }}
              formatter={(value, name) => [`${value} (${((value / total) * 100).toFixed(0)}%)`, name]}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="space-y-2 text-xs">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-accent-success" />
          <span className="text-text-secondary">Wins</span>
          <span className="font-mono text-text-primary ml-auto">{model.total_wins}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-accent-error" />
          <span className="text-text-secondary">Losses</span>
          <span className="font-mono text-text-primary ml-auto">{model.total_losses}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-accent-warning" />
          <span className="text-text-secondary">Ties</span>
          <span className="font-mono text-text-primary ml-auto">{model.total_ties}</span>
        </div>
        <div className="border-t border-border-default pt-1.5 mt-1.5">
          <span className="text-text-muted">Total: </span>
          <span className="font-mono text-text-primary">{total}</span>
        </div>
      </div>
    </div>
  )
}

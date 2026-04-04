import { useCallback, useEffect, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import api from '../lib/api'
import EloTable from '../components/leaderboard/EloTable'
import WinRateChart from '../components/leaderboard/WinRateChart'
import LatencyChart from '../components/leaderboard/LatencyChart'

export default function LeaderboardPage() {
  const [models, setModels] = useState([])
  const [stats, setStats] = useState(null)
  const [eloHistories, setEloHistories] = useState({})
  const [expandedId, setExpandedId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchData = useCallback(async () => {
    try {
      const [lbRes, statsRes] = await Promise.all([
        api.get('/leaderboard'),
        api.get('/leaderboard/stats'),
      ])
      setModels(lbRes.data.models)
      setStats(statsRes.data)

      // Fetch Elo histories for all models (for sparklines)
      const histories = {}
      await Promise.all(
        lbRes.data.models.map(async (m) => {
          try {
            const { data } = await api.get(`/leaderboard/${m.id}/history`)
            histories[m.id] = data.history
          } catch {
            histories[m.id] = []
          }
        })
      )
      setEloHistories(histories)
      setError(null)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load leaderboard')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  // Fetch expanded model's detailed history when expanding
  const handleExpand = useCallback(async (modelId) => {
    setExpandedId(modelId)
    if (modelId && !eloHistories[modelId]?.length) {
      try {
        const { data } = await api.get(`/leaderboard/${modelId}/history`)
        setEloHistories(prev => ({ ...prev, [modelId]: data.history }))
      } catch {
        // keep empty
      }
    }
  }, [eloHistories])

  // Derived stats
  const topModel = models.length > 0 ? models[0] : null
  const highestWinRate = models.length > 0
    ? models.reduce((best, m) => (m.win_rate > (best?.win_rate ?? -1) ? m : best), null)
    : null
  const totalVotes = stats
    ? stats.vote_distribution.a_wins + stats.vote_distribution.b_wins + stats.vote_distribution.ties + stats.vote_distribution.skips
    : 0

  const expandedModel = expandedId ? models.find(m => m.id === expandedId) : null
  const expandedHistory = expandedId ? (eloHistories[expandedId] || []) : []

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-text-primary mb-1">Leaderboard</h1>
        <p className="text-sm text-text-muted">Elo rankings, win rates, and latency statistics.</p>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 px-4 py-3 rounded-lg bg-accent-error/10 border border-accent-error/30 text-accent-error text-sm">
          {error}
          <button onClick={() => setError(null)} className="ml-2 opacity-60 hover:opacity-100">x</button>
        </div>
      )}

      {/* Stats summary bar */}
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
          <StatCard label="Total Battles" value={stats.total_battles} />
          <StatCard label="Total Votes" value={totalVotes} />
          <StatCard
            label="Top Model"
            value={topModel?.name || '--'}
            sub={topModel ? `Elo ${topModel.elo_rating.toFixed(0)}` : null}
          />
          <StatCard
            label="Highest Win Rate"
            value={highestWinRate && highestWinRate.total_battles > 0 ? `${highestWinRate.win_rate.toFixed(0)}%` : '--'}
            sub={highestWinRate?.total_battles > 0 ? highestWinRate.name : null}
          />
        </div>
      )}

      {/* Loading */}
      {loading ? (
        <div className="text-sm text-text-muted py-12 text-center">Loading leaderboard...</div>
      ) : (
        <>
          {/* Main table */}
          <EloTable
            models={models}
            eloHistories={eloHistories}
            expandedId={expandedId}
            onExpand={handleExpand}
          />

          {/* Expanded detail panel */}
          {expandedModel && (
            <div className="mt-1 bg-bg-secondary border border-border-default border-t-0 rounded-b-lg p-6 animate-fade-in">
              <div className="flex items-center justify-between mb-5">
                <div>
                  <h3 className="text-sm font-semibold text-text-primary">{expandedModel.name}</h3>
                  <span className="text-xs text-text-muted font-mono">{expandedModel.ollama_name}</span>
                </div>
                <button
                  onClick={() => setExpandedId(null)}
                  className="text-xs text-text-muted hover:text-text-primary transition-colors"
                >
                  Close
                </button>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Elo history chart */}
                <div className="lg:col-span-2 bg-bg-surface border border-border-default rounded-lg p-4">
                  <div className="text-[10px] text-text-muted uppercase tracking-wider mb-3">Elo Rating History</div>
                  {expandedHistory.length >= 2 ? (
                    <ResponsiveContainer width="100%" height={200}>
                      <LineChart data={expandedHistory} margin={{ top: 5, right: 20, bottom: 5, left: 10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-default)" />
                        <XAxis
                          dataKey="recorded_at"
                          stroke="var(--color-text-muted)"
                          tick={{ fontSize: 10, fontFamily: 'var(--font-mono)' }}
                          tickFormatter={(v) => {
                            const d = new Date(v)
                            return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
                          }}
                        />
                        <YAxis
                          stroke="var(--color-text-muted)"
                          tick={{ fontSize: 10, fontFamily: 'var(--font-mono)' }}
                          domain={['auto', 'auto']}
                        />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: 'var(--color-bg-secondary)',
                            border: '1px solid var(--color-border-default)',
                            borderRadius: '6px',
                            fontSize: 12,
                            fontFamily: 'var(--font-mono)',
                          }}
                          labelFormatter={(v) => new Date(v).toLocaleString()}
                          formatter={(v) => [v.toFixed(1), 'Elo']}
                        />
                        <Line
                          type="monotone"
                          dataKey="elo_rating"
                          stroke="var(--color-accent-success)"
                          strokeWidth={2}
                          dot={{ r: 3, fill: 'var(--color-accent-success)' }}
                          activeDot={{ r: 5, fill: 'var(--color-accent-success)' }}
                          isAnimationActive={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="h-[200px] flex items-center justify-center text-xs text-text-muted">
                      {expandedHistory.length === 1 ? 'Only 1 data point — need more battles for a chart' : 'No Elo history recorded yet'}
                    </div>
                  )}
                </div>

                {/* Win/Loss/Tie donut */}
                <div className="bg-bg-surface border border-border-default rounded-lg p-4">
                  <div className="text-[10px] text-text-muted uppercase tracking-wider mb-3">Win / Loss / Tie</div>
                  <WinRateChart model={expandedModel} />
                </div>
              </div>

              {/* Latency comparison */}
              <div className="mt-4 bg-bg-surface border border-border-default rounded-lg p-4">
                <div className="text-[10px] text-text-muted uppercase tracking-wider mb-3">Latency Comparison</div>
                <LatencyChart model={expandedModel} allModels={models} />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function StatCard({ label, value, sub }) {
  return (
    <div className="bg-bg-secondary border border-border-default rounded-lg px-4 py-3">
      <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1">{label}</div>
      <div className="text-lg font-mono font-bold text-text-primary truncate">{value}</div>
      {sub && <div className="text-[10px] text-text-muted mt-0.5 truncate">{sub}</div>}
    </div>
  )
}

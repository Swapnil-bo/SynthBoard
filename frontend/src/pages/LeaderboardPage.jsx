import { useCallback, useEffect, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import api from '../lib/api'
import EloTable from '../components/leaderboard/EloTable'
import WinRateChart from '../components/leaderboard/WinRateChart'
import LatencyChart from '../components/leaderboard/LatencyChart'
import { useToast } from '../components/Toast'
import { SkeletonStatCard, SkeletonTable } from '../components/Skeleton'

export default function LeaderboardPage() {
  const [models, setModels] = useState([])
  const [stats, setStats] = useState(null)
  const [eloHistories, setEloHistories] = useState({})
  const [expandedId, setExpandedId] = useState(null)
  const [loading, setLoading] = useState(true)
  const toast = useToast()

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
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to load leaderboard')
    } finally {
      setLoading(false)
    }
  }, [toast])

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

      {/* Stats summary bar */}
      {loading ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
          <SkeletonStatCard />
          <SkeletonStatCard />
          <SkeletonStatCard />
          <SkeletonStatCard />
        </div>
      ) : stats && (
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
        <SkeletonTable rows={4} cols={8} />
      ) : models.length === 0 ? (
        /* Empty state */
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <svg className="w-12 h-12 mb-4 text-text-muted opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 18.75h-9m9 0a3 3 0 0 1 3 3h-15a3 3 0 0 1 3-3m9 0v-3.375c0-.621-.503-1.125-1.125-1.125h-.871M7.5 18.75v-3.375c0-.621.504-1.125 1.125-1.125h.872m5.007 0H9.497m5.007 0a7.454 7.454 0 0 1-.982-3.172M9.497 14.25a7.454 7.454 0 0 0 .981-3.172M5.25 4.236c-.982.143-1.954.317-2.916.52A6.003 6.003 0 0 0 7.73 9.728M5.25 4.236V4.5c0 2.108.966 3.99 2.48 5.228M5.25 4.236V2.721C7.456 2.41 9.71 2.25 12 2.25c2.291 0 4.545.16 6.75.47v1.516M18.75 4.236c.982.143 1.954.317 2.916.52A6.003 6.003 0 0 1 16.27 9.728M18.75 4.236V4.5c0 2.108-.966 3.99-2.48 5.228m0 0a6.023 6.023 0 0 1-2.77.896m-5.458 0a6.024 6.024 0 0 1-2.772-.896" />
          </svg>
          <p className="text-sm text-text-muted mb-1">No battles yet</p>
          <p className="text-xs text-text-muted">
            Run some arena battles first. Go to the <a href="/arena" className="text-accent-info underline">Arena</a> to get started.
          </p>
        </div>
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

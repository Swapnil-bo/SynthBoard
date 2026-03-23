import { useCallback, useEffect, useState } from 'react'
import api from '../lib/api'
import TrainingConfig from '../components/training/TrainingConfig'
import TrainingProgress from '../components/training/TrainingProgress'

const STATUS_STYLES = {
  running: { text: 'text-accent-success', bg: 'bg-accent-success/15' },
  completed: { text: 'text-accent-success', bg: 'bg-accent-success/15' },
  failed: { text: 'text-accent-error', bg: 'bg-accent-error/15' },
  cancelled: { text: 'text-accent-warning', bg: 'bg-accent-warning/15' },
  pending: { text: 'text-text-muted', bg: 'bg-bg-surface' },
}

function formatDuration(startedAt, completedAt) {
  if (!startedAt) return '--'
  const start = new Date(startedAt)
  const end = completedAt ? new Date(completedAt) : new Date()
  const sec = Math.round((end - start) / 1000)
  if (sec < 60) return `${sec}s`
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}m ${s}s`
}

export default function TrainingPage() {
  const [runs, setRuns] = useState([])
  const [loadingRuns, setLoadingRuns] = useState(true)
  const [activeRun, setActiveRun] = useState(null)
  const [selectedRunId, setSelectedRunId] = useState(null)

  const fetchRuns = useCallback(async () => {
    try {
      const { data } = await api.get('/training/runs')
      setRuns(data)
      // Auto-select the running run if there is one
      const running = data.find(r => r.status === 'running')
      if (running) {
        setActiveRun(running)
        setSelectedRunId(running.id)
      } else if (activeRun && activeRun.status === 'running') {
        // Training just finished — refresh the active run data
        const updated = data.find(r => r.id === activeRun.id)
        if (updated) setActiveRun(updated)
      }
    } catch {
      // ignore
    } finally {
      setLoadingRuns(false)
    }
  }, [activeRun])

  useEffect(() => { fetchRuns() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleTrainingStarted = (run) => {
    setActiveRun(run)
    setSelectedRunId(run.id)
    fetchRuns()
  }

  const handleRunUpdated = () => {
    // Called when SSE receives a terminal event — refresh runs list
    fetchRuns()
  }

  const handleSelectRun = (run) => {
    setSelectedRunId(run.id)
    setActiveRun(run)
  }

  // The run shown in the dashboard
  const dashboardRun = activeRun

  return (
    <div className="flex h-full">
      {/* Left panel — config */}
      <div className="w-96 shrink-0 border-r border-border-default overflow-auto">
        <TrainingConfig onTrainingStarted={handleTrainingStarted} />
      </div>

      {/* Right panel — dashboard + history */}
      <div className="flex-1 overflow-auto">
        <div className="p-5 space-y-6">
          {/* Live dashboard (or selected run details) */}
          {dashboardRun ? (
            <div>
              <h2 className="text-lg font-semibold text-text-primary mb-1">Training Dashboard</h2>
              <p className="text-xs text-text-muted mb-4">
                {dashboardRun.status === 'running' ? 'Live training progress' : 'Run details'}
              </p>
              <TrainingProgress run={dashboardRun} onRunUpdated={handleRunUpdated} />
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-12 text-text-muted">
              <svg className="w-10 h-10 mb-3 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z" />
              </svg>
              <div className="text-sm">No active training</div>
              <div className="text-xs mt-1">Start a training run from the config panel</div>
            </div>
          )}

          {/* Training History */}
          <div>
            <h2 className="text-lg font-semibold text-text-primary mb-1">Training History</h2>
            <p className="text-xs text-text-muted mb-3">All past and current training runs</p>

            {loadingRuns ? (
              <div className="text-sm text-text-muted">Loading...</div>
            ) : runs.length === 0 ? (
              <div className="text-sm text-text-muted py-4">No training runs yet. Configure and start one on the left.</div>
            ) : (
              <div className="border border-border-default rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-bg-tertiary text-text-muted text-xs uppercase tracking-wide">
                      <th className="text-left px-4 py-2.5 font-medium">Model</th>
                      <th className="text-left px-4 py-2.5 font-medium">Status</th>
                      <th className="text-right px-4 py-2.5 font-medium">Loss</th>
                      <th className="text-right px-4 py-2.5 font-medium">Steps</th>
                      <th className="text-right px-4 py-2.5 font-medium">Duration</th>
                      <th className="text-right px-4 py-2.5 font-medium">Started</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map(run => {
                      const isSelected = selectedRunId === run.id
                      const style = STATUS_STYLES[run.status] || STATUS_STYLES.pending
                      const shortModel = run.base_model.split('/').pop()
                      return (
                        <tr
                          key={run.id}
                          onClick={() => handleSelectRun(run)}
                          className={`border-t border-border-default cursor-pointer transition-colors ${
                            isSelected ? 'bg-bg-hover' : 'hover:bg-bg-surface'
                          }`}
                        >
                          <td className="px-4 py-2.5">
                            <div className="text-text-primary">{shortModel}</div>
                            <div className="font-mono text-[10px] text-text-muted">{run.id}</div>
                          </td>
                          <td className="px-4 py-2.5">
                            <span className={`text-xs font-medium uppercase px-1.5 py-0.5 rounded ${style.bg} ${style.text}`}>
                              {run.status === 'running' && (
                                <span className="inline-block w-1.5 h-1.5 rounded-full bg-current mr-1 animate-pulse" />
                              )}
                              {run.status}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 text-right font-mono text-text-secondary">
                            {run.final_loss != null ? run.final_loss.toFixed(4) : '--'}
                          </td>
                          <td className="px-4 py-2.5 text-right font-mono text-text-secondary">
                            {run.total_steps ?? '--'}
                          </td>
                          <td className="px-4 py-2.5 text-right font-mono text-text-secondary">
                            {formatDuration(run.started_at, run.completed_at)}
                          </td>
                          <td className="px-4 py-2.5 text-right text-text-muted text-xs">
                            {run.started_at ? new Date(run.started_at).toLocaleString() : '--'}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

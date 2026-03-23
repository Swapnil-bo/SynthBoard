import { useCallback, useEffect, useState } from 'react'
import api from '../lib/api'
import TrainingConfig from '../components/training/TrainingConfig'

const STATUS_STYLES = {
  running: 'text-accent-success',
  completed: 'text-accent-info',
  failed: 'text-accent-error',
  cancelled: 'text-accent-warning',
  pending: 'text-text-muted',
}

export default function TrainingPage() {
  const [runs, setRuns] = useState([])
  const [loadingRuns, setLoadingRuns] = useState(true)

  const fetchRuns = useCallback(async () => {
    try {
      const { data } = await api.get('/training/runs')
      setRuns(data)
    } catch {
      // ignore
    } finally {
      setLoadingRuns(false)
    }
  }, [])

  useEffect(() => { fetchRuns() }, [fetchRuns])

  const handleTrainingStarted = (run) => {
    // Refresh runs list — Step 15 will add live progress tracking
    fetchRuns()
  }

  return (
    <div className="flex h-full">
      {/* Left panel — config */}
      <div className="w-96 shrink-0 border-r border-border-default overflow-auto">
        <TrainingConfig onTrainingStarted={handleTrainingStarted} />
      </div>

      {/* Right panel — history (placeholder for Step 15 dashboard) */}
      <div className="flex-1 overflow-auto">
        <div className="p-5">
          <h2 className="text-lg font-semibold text-text-primary mb-1">Training Runs</h2>
          <p className="text-xs text-text-muted mb-4">Past and active training runs</p>

          {loadingRuns ? (
            <div className="text-sm text-text-muted">Loading...</div>
          ) : runs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-text-muted">
              <svg className="w-10 h-10 mb-3 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 0 1 4.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0 1 12 15a9.065 9.065 0 0 0-6.23.693L5 14.5m14.8.8 1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0 1 12 21a48.25 48.25 0 0 1-8.134-.784c-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
              </svg>
              <div className="text-sm">No training runs yet</div>
              <div className="text-xs mt-1">Configure and start a training run on the left</div>
            </div>
          ) : (
            <div className="space-y-2">
              {runs.map(run => (
                <RunCard key={run.id} run={run} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function RunCard({ run }) {
  const statusColor = STATUS_STYLES[run.status] || 'text-text-muted'
  const shortModel = run.base_model.split('/').pop()

  return (
    <div className="bg-bg-secondary border border-border-default rounded-lg px-4 py-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-text-muted">{run.id}</span>
          <span className={`text-xs font-medium uppercase ${statusColor}`}>{run.status}</span>
        </div>
        {run.final_loss != null && (
          <span className="font-mono text-xs text-text-secondary">
            loss: {run.final_loss.toFixed(4)}
          </span>
        )}
      </div>
      <div className="flex items-center gap-3 mt-1.5">
        <span className="text-sm text-text-primary">{shortModel}</span>
        {run.total_steps && (
          <span className="text-xs text-text-muted">{run.total_steps} steps</span>
        )}
        {run.started_at && (
          <span className="text-xs text-text-muted">
            {new Date(run.started_at).toLocaleString()}
          </span>
        )}
      </div>
    </div>
  )
}

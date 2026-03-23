import { useState, useCallback, useMemo } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import useSSE from '../../hooks/useSSE'
import useGpuStats from '../../hooks/useGpuStats'
import api from '../../lib/api'

const STATUS_CONFIG = {
  running:   { label: 'Running',   color: 'text-accent-success', bgColor: 'bg-accent-success/15', pulse: true },
  completed: { label: 'Completed', color: 'text-accent-success', bgColor: 'bg-accent-success/15', pulse: false },
  failed:    { label: 'Failed',    color: 'text-accent-error',   bgColor: 'bg-accent-error/15',   pulse: false },
  cancelled: { label: 'Cancelled', color: 'text-accent-warning', bgColor: 'bg-accent-warning/15', pulse: false },
  pending:   { label: 'Pending',   color: 'text-text-muted',     bgColor: 'bg-bg-surface',        pulse: false },
}

function formatEta(seconds) {
  if (seconds == null || seconds <= 0) return '--'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  if (m > 0) return `~${m}m ${s}s`
  return `~${s}s`
}

function formatDuration(seconds) {
  if (seconds == null) return '--'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

function getVramColor(pct) {
  if (pct >= 85) return 'var(--color-accent-error)'
  if (pct >= 60) return 'var(--color-accent-warning)'
  return 'var(--color-accent-success)'
}

/**
 * Live training dashboard. Connects to SSE stream and shows:
 * - Loss curve chart
 * - Step counter + progress bar
 * - ETA, VRAM gauge, learning rate
 * - Cancel button
 * - Status badge
 */
export default function TrainingProgress({ run, onRunUpdated }) {
  const [lossData, setLossData] = useState([])
  const [latestProgress, setLatestProgress] = useState(null)
  const [terminalEvent, setTerminalEvent] = useState(null)
  const [cancelling, setCancelling] = useState(false)
  const [showCancelConfirm, setShowCancelConfirm] = useState(false)

  // Poll GPU faster during active training, slower otherwise
  const { stats: gpuStats } = useGpuStats(run?.status === 'running' ? 3000 : 10000)

  // Only connect SSE if the run is running
  const sseUrl = run?.status === 'running'
    ? `/api/training/runs/${run.id}/stream`
    : null

  const onProgress = useCallback((data) => {
    setLatestProgress(data)
    if (data.loss != null) {
      setLossData(prev => {
        // Avoid duplicate steps
        if (prev.length > 0 && prev[prev.length - 1].step === data.step) return prev
        return [...prev, { step: data.step, loss: data.loss }]
      })
    }
  }, [])

  const onComplete = useCallback((data) => {
    setTerminalEvent({ type: 'complete', data })
    onRunUpdated?.()
  }, [onRunUpdated])

  const onError = useCallback((data) => {
    setTerminalEvent({ type: 'error', data })
    onRunUpdated?.()
  }, [onRunUpdated])

  const onCancelled = useCallback((data) => {
    setTerminalEvent({ type: 'cancelled', data })
    onRunUpdated?.()
  }, [onRunUpdated])

  const onCheckpoint = useCallback(() => {}, [])

  const { connected, reconnecting } = useSSE(sseUrl, {
    onProgress,
    onComplete,
    onError,
    onCancelled,
    onCheckpoint,
  })

  // Determine displayed status
  const displayStatus = terminalEvent
    ? terminalEvent.type === 'complete' ? 'completed'
    : terminalEvent.type === 'error' ? 'failed'
    : 'cancelled'
    : run?.status || 'pending'

  const statusCfg = STATUS_CONFIG[displayStatus] || STATUS_CONFIG.pending

  // Progress values
  const currentStep = latestProgress?.step ?? 0
  const totalSteps = latestProgress?.total_steps ?? run?.total_steps ?? 0
  const progressPct = totalSteps > 0 ? Math.round((currentStep / totalSteps) * 100) : 0
  const currentLoss = latestProgress?.loss
  const currentLr = latestProgress?.learning_rate
  const etaSeconds = latestProgress?.eta_seconds

  // VRAM from SSE progress or GPU polling
  const vramUsedMb = latestProgress?.vram_used_mb ?? gpuStats?.vram_used_mb
  const vramTotalMb = gpuStats?.vram_total_mb ?? 6144
  const vramPct = vramTotalMb > 0 ? Math.round((vramUsedMb || 0) / vramTotalMb * 100) : 0

  const shortModel = run?.base_model?.split('/').pop() || 'Unknown'

  // Cancel handler
  const handleCancel = async () => {
    setShowCancelConfirm(false)
    setCancelling(true)
    try {
      await api.post(`/training/runs/${run.id}/cancel`)
    } catch {
      // Will be reflected via SSE or run refresh
    } finally {
      setCancelling(false)
    }
  }

  // Terminal message
  const terminalMessage = useMemo(() => {
    if (!terminalEvent) return null
    const d = terminalEvent.data
    if (terminalEvent.type === 'complete') {
      return `Training complete. Final loss: ${d.final_loss?.toFixed(4) ?? '?'}. Time: ${formatDuration(d.total_time_seconds)}.`
    }
    if (terminalEvent.type === 'error') {
      return `Training failed: ${d.message || 'Unknown error'}`
    }
    if (terminalEvent.type === 'cancelled') {
      return `Training cancelled at step ${d.step ?? '?'}/${d.total_steps ?? '?'}. Time: ${formatDuration(d.total_time_seconds)}.`
    }
    return null
  }, [terminalEvent])

  if (!run) return null

  return (
    <div className="space-y-4">
      {/* Header: model name + status badge */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-semibold text-text-primary">{shortModel}</h3>
          <span className={`text-xs font-medium uppercase px-2 py-0.5 rounded ${statusCfg.bgColor} ${statusCfg.color}`}>
            {statusCfg.pulse && <span className="inline-block w-1.5 h-1.5 rounded-full bg-current mr-1.5 animate-pulse" />}
            {statusCfg.label}
          </span>
          {connected && (
            <span className="text-[10px] text-text-muted">SSE connected</span>
          )}
          {reconnecting && (
            <span className="text-[10px] text-accent-warning">Reconnecting...</span>
          )}
        </div>
        <span className="font-mono text-[10px] text-text-muted">{run.id}</span>
      </div>

      {/* Step counter + progress bar */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="font-mono text-sm text-text-primary">
            Step {currentStep} / {totalSteps}
          </span>
          <span className="font-mono text-sm text-text-secondary">{progressPct}%</span>
        </div>
        <div className="w-full h-2 bg-bg-primary rounded-full overflow-hidden border border-border-default">
          <div
            className="h-full rounded-full transition-all duration-500 ease-out"
            style={{
              width: `${progressPct}%`,
              backgroundColor: displayStatus === 'failed' ? 'var(--color-accent-error)'
                : displayStatus === 'cancelled' ? 'var(--color-accent-warning)'
                : 'var(--color-accent-success)',
            }}
          />
        </div>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <MetricCard label="Loss" value={currentLoss?.toFixed(4) ?? '--'} mono />
        <MetricCard label="Learning Rate" value={currentLr != null ? currentLr.toExponential(2) : '--'} mono />
        <MetricCard label="ETA" value={formatEta(etaSeconds)} />
        {/* VRAM gauge */}
        <div className="bg-bg-surface border border-border-default rounded-lg px-3 py-2">
          <div className="text-[10px] text-text-muted uppercase tracking-wide mb-0.5">VRAM</div>
          <div className="flex items-center gap-2">
            <div className="flex-1 h-2 bg-bg-primary rounded-full overflow-hidden border border-border-default">
              <div
                className="h-full rounded-full transition-all duration-700 ease-out"
                style={{ width: `${vramPct}%`, backgroundColor: getVramColor(vramPct) }}
              />
            </div>
            <span className="font-mono text-xs text-text-secondary whitespace-nowrap">
              {vramUsedMb != null ? `${(vramUsedMb / 1024).toFixed(1)}G` : '--'}
            </span>
          </div>
        </div>
      </div>

      {/* Loss curve chart */}
      <div className="bg-bg-surface border border-border-default rounded-lg p-4">
        <div className="text-xs text-text-muted uppercase tracking-wide mb-3">Loss Curve</div>
        {lossData.length > 0 ? (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={lossData} margin={{ top: 5, right: 20, bottom: 5, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-default)" />
              <XAxis
                dataKey="step"
                stroke="var(--color-text-muted)"
                tick={{ fontSize: 11, fontFamily: 'var(--font-mono)' }}
                label={{ value: 'Step', position: 'insideBottom', offset: -2, fontSize: 10, fill: 'var(--color-text-muted)' }}
              />
              <YAxis
                stroke="var(--color-text-muted)"
                tick={{ fontSize: 11, fontFamily: 'var(--font-mono)' }}
                label={{ value: 'Loss', angle: -90, position: 'insideLeft', offset: 5, fontSize: 10, fill: 'var(--color-text-muted)' }}
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
                labelStyle={{ color: 'var(--color-text-muted)' }}
                itemStyle={{ color: 'var(--color-accent-success)' }}
                formatter={(value) => [value.toFixed(4), 'Loss']}
                labelFormatter={(label) => `Step ${label}`}
              />
              <Line
                type="monotone"
                dataKey="loss"
                stroke="var(--color-accent-success)"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, fill: 'var(--color-accent-success)' }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-[220px] flex items-center justify-center text-sm text-text-muted">
            {displayStatus === 'running' ? 'Waiting for first loss value...' : 'No loss data recorded'}
          </div>
        )}
      </div>

      {/* Terminal message */}
      {terminalMessage && (
        <div className={`rounded-lg px-4 py-3 text-sm ${
          terminalEvent?.type === 'complete'
            ? 'bg-accent-success/10 border border-accent-success/30 text-accent-success'
            : terminalEvent?.type === 'error'
            ? 'bg-accent-error/10 border border-accent-error/30 text-accent-error'
            : 'bg-accent-warning/10 border border-accent-warning/30 text-accent-warning'
        }`}>
          {terminalMessage}
        </div>
      )}

      {/* Cancel button */}
      {displayStatus === 'running' && (
        <div>
          {showCancelConfirm ? (
            <div className="flex items-center gap-3 bg-accent-error/10 border border-accent-error/30 rounded-lg px-4 py-3">
              <span className="text-sm text-accent-error">Cancel this training run?</span>
              <button
                onClick={handleCancel}
                disabled={cancelling}
                className="px-3 py-1 text-xs font-medium rounded bg-accent-error/20 text-accent-error border border-accent-error/40 hover:bg-accent-error/30 disabled:opacity-50"
              >
                {cancelling ? 'Cancelling...' : 'Yes, cancel'}
              </button>
              <button
                onClick={() => setShowCancelConfirm(false)}
                className="px-3 py-1 text-xs font-medium rounded bg-bg-surface text-text-secondary border border-border-default hover:bg-bg-hover"
              >
                No, continue
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowCancelConfirm(true)}
              className="px-4 py-2 text-xs font-medium rounded-lg bg-accent-error/10 text-accent-error border border-accent-error/30 hover:bg-accent-error/20 transition-colors"
            >
              Cancel Training
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function MetricCard({ label, value, mono }) {
  return (
    <div className="bg-bg-surface border border-border-default rounded-lg px-3 py-2">
      <div className="text-[10px] text-text-muted uppercase tracking-wide mb-0.5">{label}</div>
      <div className={`text-sm text-text-primary ${mono ? 'font-mono' : ''}`}>{value}</div>
    </div>
  )
}

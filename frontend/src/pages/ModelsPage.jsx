import { useCallback, useEffect, useState } from 'react'
import api from '../lib/api'

const SOURCE_BADGES = {
  base: { label: 'Base', bg: 'bg-accent-info/15', text: 'text-accent-info' },
  'fine-tuned': { label: 'Fine-tuned', bg: 'bg-accent-success/15', text: 'text-accent-success' },
}

function formatSize(bytes) {
  if (!bytes) return '--'
  const gb = bytes / (1024 * 1024 * 1024)
  if (gb >= 1) return `${gb.toFixed(1)} GB`
  return `${(bytes / (1024 * 1024)).toFixed(0)} MB`
}

export default function ModelsPage() {
  const [models, setModels] = useState([])
  const [loading, setLoading] = useState(true)
  const [exportableRuns, setExportableRuns] = useState([])
  const [showRegister, setShowRegister] = useState(false)
  const [showExport, setShowExport] = useState(false)
  const [deleting, setDeleting] = useState(null)
  const [exporting, setExporting] = useState(null)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)

  const fetchModels = useCallback(async () => {
    try {
      const { data } = await api.get('/models')
      setModels(data)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchExportableRuns = useCallback(async () => {
    try {
      const { data } = await api.get('/models/exportable-runs')
      setExportableRuns(data.runs)
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    fetchModels()
    fetchExportableRuns()
  }, [fetchModels, fetchExportableRuns])

  const handleDelete = async (model, deleteGguf = false) => {
    if (!confirm(`Remove "${model.name}" from the arena?${deleteGguf ? ' This will also delete the GGUF file.' : ''}`)) return
    setDeleting(model.id)
    setError(null)
    try {
      await api.delete(`/models/${model.id}?delete_gguf=${deleteGguf}`)
      setSuccess(`Removed "${model.name}"`)
      fetchModels()
      fetchExportableRuns()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete model')
    } finally {
      setDeleting(null)
      setTimeout(() => setSuccess(null), 3000)
    }
  }

  const handleExport = async (runId) => {
    setExporting(runId)
    setError(null)
    try {
      const { data } = await api.post(`/models/export/${runId}`, {}, { timeout: 600000 })
      setSuccess(`Exported! Model: ${data.ollama_model_name}`)
      setShowExport(false)
      fetchModels()
      fetchExportableRuns()
    } catch (err) {
      setError(err.response?.data?.detail || 'Export failed')
    } finally {
      setExporting(null)
      setTimeout(() => setSuccess(null), 5000)
    }
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary mb-1">Models</h1>
          <p className="text-sm text-text-muted">Model registry, GGUF export, and Ollama management.</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => { setShowExport(true); setShowRegister(false) }}
            className="px-3 py-2 text-sm font-medium rounded-lg bg-accent-success/15 text-accent-success hover:bg-accent-success/25 transition-colors"
          >
            Export to Arena
          </button>
          <button
            onClick={() => { setShowRegister(true); setShowExport(false) }}
            className="px-3 py-2 text-sm font-medium rounded-lg bg-accent-info/15 text-accent-info hover:bg-accent-info/25 transition-colors"
          >
            Register Base Model
          </button>
        </div>
      </div>

      {/* Notifications */}
      {error && (
        <div className="mb-4 px-4 py-3 rounded-lg bg-accent-error/10 border border-accent-error/30 text-accent-error text-sm">
          {error}
          <button onClick={() => setError(null)} className="ml-2 opacity-60 hover:opacity-100">✕</button>
        </div>
      )}
      {success && (
        <div className="mb-4 px-4 py-3 rounded-lg bg-accent-success/10 border border-accent-success/30 text-accent-success text-sm">
          {success}
        </div>
      )}

      {/* Register Base Model Panel */}
      {showRegister && (
        <RegisterBaseModelPanel
          onRegistered={() => { setShowRegister(false); fetchModels() }}
          onCancel={() => setShowRegister(false)}
          onError={setError}
        />
      )}

      {/* Export Panel */}
      {showExport && (
        <ExportPanel
          runs={exportableRuns}
          exporting={exporting}
          onExport={handleExport}
          onCancel={() => setShowExport(false)}
        />
      )}

      {/* Model List */}
      {loading ? (
        <div className="text-sm text-text-muted py-8 text-center">Loading models...</div>
      ) : models.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid gap-3">
          {models.map(model => (
            <ModelCard
              key={model.id}
              model={model}
              deleting={deleting === model.id}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Model Card ──────────────────────────────────────────────────────────────

function ModelCard({ model, deleting, onDelete }) {
  const badge = SOURCE_BADGES[model.source] || SOURCE_BADGES.base
  const winRate = model.total_battles > 0
    ? ((model.total_wins / model.total_battles) * 100).toFixed(0)
    : null

  return (
    <div className="bg-bg-secondary border border-border-default rounded-lg p-4 hover:border-border-subtle transition-colors">
      <div className="flex items-start justify-between gap-4">
        {/* Left: info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-sm font-semibold text-text-primary truncate">{model.name}</h3>
            <span className={`text-xs font-medium px-1.5 py-0.5 rounded ${badge.bg} ${badge.text} shrink-0`}>
              {badge.label}
            </span>
          </div>
          <div className="flex items-center gap-3 text-xs text-text-muted mt-1">
            <span className="font-mono">{model.ollama_name}</span>
            {model.training_run_id && (
              <span>Run: <span className="font-mono">{model.training_run_id}</span></span>
            )}
          </div>
        </div>

        {/* Right: stats + actions */}
        <div className="flex items-center gap-4 shrink-0">
          {/* Stats */}
          <div className="flex items-center gap-4 text-right">
            <Stat label="Elo" value={model.elo_rating.toFixed(0)} highlight />
            <Stat label="Battles" value={model.total_battles} />
            {winRate !== null && <Stat label="Win %" value={`${winRate}%`} />}
            {model.avg_tps != null && <Stat label="TPS" value={model.avg_tps.toFixed(1)} />}
          </div>

          {/* Delete button */}
          <button
            onClick={() => onDelete(model, model.source === 'fine-tuned')}
            disabled={deleting}
            className="text-text-muted hover:text-accent-error text-xs transition-colors px-2 py-1 rounded hover:bg-accent-error/10 disabled:opacity-50"
            title={model.source === 'fine-tuned' ? 'Remove from arena + delete GGUF' : 'Remove from arena'}
          >
            {deleting ? '...' : 'Remove'}
          </button>
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value, highlight }) {
  return (
    <div>
      <div className="text-[10px] text-text-muted uppercase tracking-wide">{label}</div>
      <div className={`text-sm font-mono ${highlight ? 'text-accent-info font-semibold' : 'text-text-secondary'}`}>
        {value}
      </div>
    </div>
  )
}

// ─── Register Base Model Panel ───────────────────────────────────────────────

function RegisterBaseModelPanel({ onRegistered, onCancel, onError }) {
  const [ollamaModels, setOllamaModels] = useState([])
  const [loadingOllama, setLoadingOllama] = useState(true)
  const [ollamaError, setOllamaError] = useState(null)
  const [selectedModel, setSelectedModel] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    async function fetch() {
      try {
        const { data } = await api.get('/models/available')
        setOllamaModels(data.models)
        setOllamaError(null)
      } catch (err) {
        setOllamaError(
          err.response?.data?.detail || 'Cannot connect to Ollama. Is it running?'
        )
      } finally {
        setLoadingOllama(false)
      }
    }
    fetch()
  }, [])

  const handleSelect = (name) => {
    setSelectedModel(name)
    // Auto-fill display name from model name
    setDisplayName(name.split(':')[0])
  }

  const handleSubmit = async () => {
    if (!selectedModel || !displayName.trim()) return
    setSubmitting(true)
    try {
      await api.post('/models/register-base', {
        name: displayName.trim(),
        ollama_name: selectedModel,
      })
      onRegistered()
    } catch (err) {
      onError(err.response?.data?.detail || 'Failed to register model')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mb-6 bg-bg-secondary border border-accent-info/30 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-accent-info">Register Base Model from Ollama</h3>
        <button onClick={onCancel} className="text-text-muted hover:text-text-primary text-xs">Cancel</button>
      </div>

      {loadingOllama ? (
        <div className="text-sm text-text-muted py-2">Fetching installed Ollama models...</div>
      ) : ollamaError ? (
        <div className="text-sm text-accent-error py-2">{ollamaError}</div>
      ) : ollamaModels.length === 0 ? (
        <div className="text-sm text-text-muted py-2">
          No models found in Ollama. Pull a model first: <code className="font-mono text-accent-info">ollama pull qwen2.5:1.5b</code>
        </div>
      ) : (
        <div>
          <div className="text-xs text-text-muted mb-2">Select a model to register for the arena:</div>
          <div className="grid gap-2 max-h-60 overflow-auto mb-3">
            {ollamaModels.map(m => (
              <button
                key={m.name}
                onClick={() => handleSelect(m.name)}
                className={`text-left px-3 py-2 rounded-lg border transition-colors text-sm ${
                  selectedModel === m.name
                    ? 'border-accent-info/50 bg-accent-info/10'
                    : 'border-border-default hover:border-border-subtle hover:bg-bg-tertiary'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-text-primary">{m.name}</span>
                  <span className="text-xs text-text-muted">{formatSize(m.size)}</span>
                </div>
                {(m.parameter_size || m.family) && (
                  <div className="flex gap-3 mt-0.5 text-xs text-text-muted">
                    {m.parameter_size && <span>{m.parameter_size}</span>}
                    {m.family && <span>{m.family}</span>}
                    {m.quantization_level && <span>{m.quantization_level}</span>}
                  </div>
                )}
              </button>
            ))}
          </div>

          {selectedModel && (
            <div className="flex items-end gap-3">
              <div className="flex-1">
                <label className="text-xs text-text-muted block mb-1">Display Name</label>
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  className="w-full px-3 py-2 text-sm bg-bg-primary border border-border-default rounded-lg text-text-primary focus:border-accent-info focus:outline-none"
                  placeholder="e.g. Qwen 2.5 7B"
                />
              </div>
              <button
                onClick={handleSubmit}
                disabled={submitting || !displayName.trim()}
                className="px-4 py-2 text-sm font-medium rounded-lg bg-accent-info text-bg-primary hover:bg-accent-info/80 disabled:opacity-50 transition-colors"
              >
                {submitting ? 'Registering...' : 'Register'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Export Panel ─────────────────────────────────────────────────────────────

function ExportPanel({ runs, exporting, onExport, onCancel }) {
  return (
    <div className="mb-6 bg-bg-secondary border border-accent-success/30 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-accent-success">Export Fine-tuned Model to Arena</h3>
        <button onClick={onCancel} className="text-text-muted hover:text-text-primary text-xs">Cancel</button>
      </div>

      {runs.length === 0 ? (
        <div className="text-sm text-text-muted py-2">
          No exportable training runs. Complete a training run first, then export it here.
        </div>
      ) : (
        <div className="space-y-2">
          <div className="text-xs text-text-muted mb-2">Completed training runs ready for GGUF export:</div>
          {runs.map(run => {
            const shortModel = run.base_model.split('/').pop()
            const isExporting = exporting === run.id
            return (
              <div
                key={run.id}
                className="flex items-center justify-between px-3 py-2 rounded-lg border border-border-default bg-bg-tertiary"
              >
                <div>
                  <div className="text-sm text-text-primary">{shortModel}</div>
                  <div className="flex gap-3 text-xs text-text-muted mt-0.5">
                    <span className="font-mono">{run.id}</span>
                    {run.final_loss != null && <span>Loss: {run.final_loss.toFixed(4)}</span>}
                    {run.total_steps && <span>{run.total_steps} steps</span>}
                  </div>
                </div>
                <button
                  onClick={() => onExport(run.id)}
                  disabled={!!exporting}
                  className="px-3 py-1.5 text-xs font-medium rounded-lg bg-accent-success text-bg-primary hover:bg-accent-success/80 disabled:opacity-50 transition-colors"
                >
                  {isExporting ? 'Exporting...' : 'Export GGUF'}
                </button>
              </div>
            )
          })}
          {exporting && (
            <div className="text-xs text-accent-warning mt-2">
              Export in progress... This may take several minutes (model merge + GGUF conversion).
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Empty State ─────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <svg className="w-12 h-12 mb-4 text-text-muted opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75m16.5 0c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125" />
      </svg>
      <p className="text-sm text-text-muted mb-1">No models registered</p>
      <p className="text-xs text-text-muted">
        Export a fine-tuned model or register a base model to get started.
      </p>
    </div>
  )
}

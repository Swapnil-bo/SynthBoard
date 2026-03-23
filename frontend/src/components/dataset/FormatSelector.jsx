import { useState } from 'react'
import api from '../../lib/api'

export default function FormatSelector({ dataset, onFormatted }) {
  const [mapping, setMapping] = useState({ instruction: '', output: '', input: '' })
  const [formatting, setFormatting] = useState(false)
  const [error, setError] = useState(null)

  if (!dataset || dataset.format_detected !== 'unknown') return null

  // Extract column names from the raw preview
  const columns = []
  if (dataset.preview?.length > 0) {
    const raw = dataset.preview[0].raw || dataset.preview[0]
    for (const k of Object.keys(raw)) {
      if (k !== 'instruction' && k !== 'input' && k !== 'output' && k !== 'raw') {
        columns.push(k)
      }
    }
  }

  if (columns.length === 0) return null

  const handleFormat = async () => {
    if (!mapping.instruction && !mapping.output) {
      setError('Map at least instruction or output.')
      return
    }
    setFormatting(true)
    setError(null)
    try {
      const body = { column_mapping: {} }
      if (mapping.instruction) body.column_mapping.instruction = mapping.instruction
      if (mapping.output) body.column_mapping.output = mapping.output
      if (mapping.input) body.column_mapping.input = mapping.input
      await api.post(`/datasets/${dataset.id}/format`, body)
      onFormatted?.()
    } catch (err) {
      setError(err.response?.data?.detail || 'Format failed')
    } finally {
      setFormatting(false)
    }
  }

  return (
    <div className="bg-bg-tertiary border border-border-default rounded-lg p-4 mt-3">
      <div className="text-sm font-medium text-accent-warning mb-3">
        Unknown format — map columns manually
      </div>
      <div className="grid grid-cols-3 gap-3">
        {['instruction', 'output', 'input'].map(field => (
          <div key={field}>
            <label className="block text-xs text-text-muted mb-1">{field}</label>
            <select
              value={mapping[field]}
              onChange={e => setMapping(m => ({ ...m, [field]: e.target.value }))}
              className="w-full bg-bg-primary border border-border-default rounded px-2 py-1.5 text-xs text-text-primary"
            >
              <option value="">— skip —</option>
              {columns.map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
        ))}
      </div>
      <button
        onClick={handleFormat}
        disabled={formatting}
        className="mt-3 px-4 py-1.5 bg-accent-info/20 text-accent-info text-xs font-medium rounded hover:bg-accent-info/30 disabled:opacity-50 transition-colors"
      >
        {formatting ? 'Formatting...' : 'Apply Mapping & Format'}
      </button>
      {error && <div className="mt-2 text-xs text-accent-error">{error}</div>}
    </div>
  )
}

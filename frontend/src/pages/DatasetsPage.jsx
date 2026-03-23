import { useCallback, useEffect, useState } from 'react'
import api from '../lib/api'
import UploadZone from '../components/dataset/UploadZone'
import DataPreview from '../components/dataset/DataPreview'
import FormatSelector from '../components/dataset/FormatSelector'

const FORMAT_BADGES = {
  alpaca: { label: 'Alpaca', color: 'text-accent-success' },
  sharegpt: { label: 'ShareGPT', color: 'text-accent-info' },
  qa: { label: 'Q&A', color: 'text-accent-info' },
  raw: { label: 'Raw', color: 'text-text-muted' },
  unknown: { label: 'Unknown', color: 'text-accent-warning' },
}

export default function DatasetsPage() {
  const [datasets, setDatasets] = useState([])
  const [selected, setSelected] = useState(null) // full dataset detail
  const [selectedId, setSelectedId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState(null)

  const fetchList = useCallback(async () => {
    try {
      const { data } = await api.get('/datasets')
      setDatasets(data.datasets)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchDetail = useCallback(async (id) => {
    try {
      const { data } = await api.get(`/datasets/${id}`)
      setSelected(data)
    } catch {
      setSelected(null)
    }
  }, [])

  useEffect(() => { fetchList() }, [fetchList])

  useEffect(() => {
    if (selectedId) fetchDetail(selectedId)
    else setSelected(null)
  }, [selectedId, fetchDetail])

  const handleUploaded = (data) => {
    fetchList()
    setSelectedId(data.id)
  }

  const handleDelete = async (e, id) => {
    e.stopPropagation()
    setDeleting(id)
    try {
      await api.delete(`/datasets/${id}`)
      if (selectedId === id) {
        setSelectedId(null)
        setSelected(null)
      }
      fetchList()
    } catch {
      // ignore
    } finally {
      setDeleting(null)
    }
  }

  return (
    <div className="flex h-full">
      {/* Left panel — list */}
      <div className="w-80 shrink-0 border-r border-border-default flex flex-col">
        <div className="p-4">
          <UploadZone onUploaded={handleUploaded} />
        </div>

        <div className="flex-1 overflow-auto">
          {loading ? (
            <div className="p-4 text-sm text-text-muted">Loading...</div>
          ) : datasets.length === 0 ? (
            <div className="p-4 text-center">
              <div className="text-sm text-text-muted">No datasets yet</div>
              <div className="text-xs text-text-muted mt-1">Upload one to get started</div>
            </div>
          ) : (
            <ul className="divide-y divide-border-subtle">
              {datasets.map(ds => {
                const badge = FORMAT_BADGES[ds.format_detected] || FORMAT_BADGES.unknown
                const isSelected = selectedId === ds.id
                return (
                  <li
                    key={ds.id}
                    onClick={() => setSelectedId(ds.id)}
                    className={`px-4 py-3 cursor-pointer transition-colors ${
                      isSelected ? 'bg-bg-hover' : 'hover:bg-bg-tertiary'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-text-primary truncate max-w-[180px]">
                        {ds.original_filename}
                      </span>
                      <button
                        onClick={(e) => handleDelete(e, ds.id)}
                        disabled={deleting === ds.id}
                        className="text-text-muted hover:text-accent-error text-xs transition-colors ml-2 shrink-0"
                        title="Delete dataset"
                      >
                        {deleting === ds.id ? '...' : '✕'}
                      </button>
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className={`text-xs font-medium ${badge.color}`}>{badge.label}</span>
                      <span className="text-xs text-text-muted">{ds.num_samples} samples</span>
                      <span className="text-xs text-text-muted">~{ds.avg_token_length} tok</span>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </div>

      {/* Right panel — detail */}
      <div className="flex-1 overflow-auto">
        {selected ? (
          <div className="p-5">
            <div className="mb-4">
              <h2 className="text-lg font-semibold text-text-primary">{selected.original_filename}</h2>
              <div className="flex items-center gap-4 mt-2">
                <Stat label="Format" value={(FORMAT_BADGES[selected.format_detected] || FORMAT_BADGES.unknown).label} />
                <Stat label="Samples" value={selected.num_samples} />
                <Stat label="Avg tokens" value={selected.avg_token_length} />
                <Stat label="ID" value={selected.id} mono />
              </div>
            </div>

            <FormatSelector
              dataset={selected}
              onFormatted={() => fetchDetail(selectedId)}
            />

            <div className="mt-4">
              <h3 className="text-xs font-medium text-text-muted uppercase tracking-wide mb-2">
                Preview (first {selected.preview?.length || 0} rows)
              </h3>
              <div className="bg-bg-secondary border border-border-default rounded-lg overflow-hidden">
                <DataPreview
                  preview={selected.preview}
                  format={selected.format_detected}
                />
              </div>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-full text-text-muted text-sm">
            {datasets.length > 0
              ? 'Select a dataset to view details'
              : 'Upload a dataset to get started'}
          </div>
        )}
      </div>
    </div>
  )
}

function Stat({ label, value, mono }) {
  return (
    <div>
      <div className="text-xs text-text-muted">{label}</div>
      <div className={`text-sm text-text-primary ${mono ? 'font-mono' : ''}`}>{value}</div>
    </div>
  )
}

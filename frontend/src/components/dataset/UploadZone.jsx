import { useCallback, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import api from '../../lib/api'

const ACCEPT = {
  'text/csv': ['.csv'],
  'application/json': ['.json', '.jsonl'],
  'application/x-ndjson': ['.jsonl'],
  'application/octet-stream': ['.parquet'],
}

export default function UploadZone({ onUploaded }) {
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(null)

  const onDrop = useCallback(async (acceptedFiles) => {
    if (acceptedFiles.length === 0) return
    const file = acceptedFiles[0]
    setUploading(true)
    setError(null)

    try {
      const form = new FormData()
      form.append('file', file)
      const { data } = await api.post('/datasets/upload', form, {
        timeout: 60000,
      })
      // Auto-format after upload
      try {
        await api.post(`/datasets/${data.id}/format`)
      } catch {
        // Non-fatal — user can format manually later
      }
      onUploaded?.(data)
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Upload failed'
      setError(msg)
    } finally {
      setUploading(false)
    }
  }, [onUploaded])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPT,
    maxFiles: 1,
    disabled: uploading,
  })

  return (
    <div
      {...getRootProps()}
      className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
        uploading
          ? 'border-border-default bg-bg-tertiary opacity-60 cursor-wait'
          : isDragActive
            ? 'border-accent-success bg-accent-success/5'
            : 'border-border-default hover:border-text-muted bg-bg-tertiary'
      }`}
    >
      <input {...getInputProps()} />
      {uploading ? (
        <div>
          <div className="text-sm text-text-secondary">Uploading & formatting...</div>
          <div className="mt-2 w-32 h-1.5 bg-bg-primary rounded-full mx-auto overflow-hidden">
            <div className="h-full bg-accent-success rounded-full animate-pulse" style={{ width: '60%' }} />
          </div>
        </div>
      ) : (
        <div>
          <div className="text-sm text-text-secondary">
            {isDragActive ? 'Drop file here...' : 'Drag & drop a dataset, or click to browse'}
          </div>
          <div className="text-xs text-text-muted mt-1">.csv, .jsonl, .json, .parquet</div>
        </div>
      )}
      {error && (
        <div className="mt-2 text-xs text-accent-error">{error}</div>
      )}
    </div>
  )
}

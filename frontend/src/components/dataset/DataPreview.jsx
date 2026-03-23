export default function DataPreview({ preview, format }) {
  if (!preview || preview.length === 0) {
    return (
      <div className="text-sm text-text-muted italic p-4">
        No preview available.
      </div>
    )
  }

  // For alpaca format, show instruction/input/output columns
  if (format === 'alpaca') {
    return (
      <div className="overflow-auto">
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="border-b border-border-default text-text-muted text-left">
              <th className="px-3 py-2 w-8">#</th>
              <th className="px-3 py-2">instruction</th>
              <th className="px-3 py-2">input</th>
              <th className="px-3 py-2">output</th>
            </tr>
          </thead>
          <tbody>
            {preview.map((row, i) => (
              <tr key={i} className="border-b border-border-subtle hover:bg-bg-hover">
                <td className="px-3 py-2 text-text-muted">{i + 1}</td>
                <td className="px-3 py-2 text-text-primary max-w-xs truncate">{row.instruction}</td>
                <td className="px-3 py-2 text-text-secondary max-w-xs truncate">{row.input || '—'}</td>
                <td className="px-3 py-2 text-text-secondary max-w-xs truncate">{row.output}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  // For other formats, show raw keys as columns
  const rows = preview.map(r => r.raw || r)
  const keys = rows.length > 0 ? Object.keys(rows[0]) : []

  return (
    <div className="overflow-auto">
      <table className="w-full text-xs font-mono">
        <thead>
          <tr className="border-b border-border-default text-text-muted text-left">
            <th className="px-3 py-2 w-8">#</th>
            {keys.map(k => (
              <th key={k} className="px-3 py-2">{k}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-border-subtle hover:bg-bg-hover">
              <td className="px-3 py-2 text-text-muted">{i + 1}</td>
              {keys.map(k => (
                <td key={k} className="px-3 py-2 text-text-primary max-w-xs truncate">
                  {typeof row[k] === 'object' ? JSON.stringify(row[k]) : String(row[k] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

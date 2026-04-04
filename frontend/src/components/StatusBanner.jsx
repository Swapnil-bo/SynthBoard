/**
 * Reusable banners for system status warnings.
 */

export function OllamaBanner({ onDismiss }) {
  return (
    <div className="mb-4 px-4 py-3 rounded-lg bg-accent-warning/10 border border-accent-warning/30 flex items-center gap-3">
      <svg className="w-5 h-5 text-accent-warning shrink-0" viewBox="0 0 20 20" fill="currentColor">
        <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
      </svg>
      <div className="flex-1">
        <span className="text-sm text-accent-warning font-medium">Ollama is not running.</span>
        <span className="text-sm text-text-muted ml-1">Start it to use the arena and model features.</span>
      </div>
      {onDismiss && (
        <button onClick={onDismiss} className="text-text-muted hover:text-text-primary text-xs">Dismiss</button>
      )}
    </div>
  )
}

export function DiskWarningBanner({ freeMb }) {
  return (
    <div className="mb-4 px-4 py-3 rounded-lg bg-accent-warning/10 border border-accent-warning/30 flex items-center gap-3">
      <svg className="w-5 h-5 text-accent-warning shrink-0" viewBox="0 0 20 20" fill="currentColor">
        <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
      </svg>
      <div className="flex-1">
        <span className="text-sm text-accent-warning font-medium">Low disk space.</span>
        <span className="text-sm text-text-muted ml-1">
          Only {freeMb < 1000 ? `${Math.round(freeMb)} MB` : `${(freeMb / 1024).toFixed(1)} GB`} free.
          Consider cleaning up old checkpoints and exports.
        </span>
      </div>
    </div>
  )
}

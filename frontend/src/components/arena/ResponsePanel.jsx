/**
 * ResponsePanel — displays one side of an arena battle.
 *
 * States driven by `status` prop:
 *   idle       – empty placeholder
 *   generating – pulsing green dot, "Generating..."
 *   waiting    – dimmed, "Waiting..."
 *   done       – response text + latency badges
 */
export default function ResponsePanel({
  label,          // "Model A" or "Model B"
  status = 'idle',
  response = '',
  ttftMs = null,
  totalMs = null,
  tokens = null,
  modelName = null,  // revealed after voting
  eloChange = null,  // e.g. +16.0 or -16.0
  winner = false,    // highlight if this panel won
}) {
  const isActive = status === 'generating'
  const isWaiting = status === 'waiting'
  const isDone = status === 'done'
  const isIdle = status === 'idle'

  const tps = (tokens && totalMs > 0) ? ((tokens * 1000) / totalMs).toFixed(1) : null

  return (
    <div
      className={`flex-1 min-w-0 flex flex-col rounded-lg border transition-colors ${
        winner
          ? 'border-accent-success/50 bg-accent-success/5'
          : isActive
            ? 'border-accent-success/30 bg-bg-secondary'
            : 'border-border-default bg-bg-secondary'
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border-default">
        <div className="flex items-center gap-2">
          {/* Status indicator */}
          {isActive && (
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent-success opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-accent-success" />
            </span>
          )}
          {isWaiting && (
            <span className="h-2.5 w-2.5 rounded-full bg-text-muted/40" />
          )}
          {isDone && (
            <span className="h-2.5 w-2.5 rounded-full bg-accent-success" />
          )}

          <span className={`text-sm font-semibold ${isWaiting ? 'text-text-muted' : 'text-text-primary'}`}>
            {label}
          </span>

          {isActive && (
            <span className="text-xs text-accent-success animate-pulse">Generating...</span>
          )}
          {isWaiting && (
            <span className="text-xs text-text-muted">Waiting...</span>
          )}
        </div>

        {/* Latency badges */}
        {isDone && (ttftMs != null || tps != null) && (
          <div className="flex items-center gap-2">
            {ttftMs != null && (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-bg-tertiary text-text-muted border border-border-default">
                TTFT {(ttftMs / 1000).toFixed(1)}s
              </span>
            )}
            {tps != null && (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-bg-tertiary text-text-muted border border-border-default">
                {tps} tok/s
              </span>
            )}
            {tokens != null && (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-bg-tertiary text-text-muted border border-border-default">
                {tokens} tok
              </span>
            )}
          </div>
        )}
      </div>

      {/* Model reveal bar (after voting) */}
      {modelName && (
        <div className="flex items-center justify-between px-4 py-2 border-b border-border-default bg-bg-tertiary/50 animate-fade-in">
          <span className="text-xs font-semibold text-accent-info font-mono">{modelName}</span>
          {eloChange != null && (
            <span className={`text-xs font-mono font-semibold ${
              eloChange > 0 ? 'text-accent-success' : eloChange < 0 ? 'text-accent-error' : 'text-text-muted'
            }`}>
              {eloChange > 0 ? '+' : ''}{eloChange.toFixed(1)}
            </span>
          )}
        </div>
      )}

      {/* Response body */}
      <div className={`flex-1 p-4 overflow-auto min-h-[200px] max-h-[500px] ${isWaiting ? 'opacity-40' : ''}`}>
        {isIdle && (
          <div className="flex items-center justify-center h-full text-text-muted text-sm">
            Submit a prompt to start
          </div>
        )}

        {(isActive || isWaiting) && !response && (
          <div className="flex items-center justify-center h-full">
            {isActive ? (
              <div className="flex gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-accent-success animate-bounce [animation-delay:0ms]" />
                <span className="w-1.5 h-1.5 rounded-full bg-accent-success animate-bounce [animation-delay:150ms]" />
                <span className="w-1.5 h-1.5 rounded-full bg-accent-success animate-bounce [animation-delay:300ms]" />
              </div>
            ) : (
              <span className="text-xs text-text-muted">Waiting for Model A to finish...</span>
            )}
          </div>
        )}

        {response && (
          <pre className="text-sm text-text-secondary font-mono whitespace-pre-wrap break-words leading-relaxed m-0">
            {response}
          </pre>
        )}
      </div>
    </div>
  )
}

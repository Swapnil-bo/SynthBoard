/**
 * VoteButtons — four vote options for an arena battle.
 *
 * "A is Better" / "Tie" / "B is Better" / "Skip"
 * Disabled until both responses are loaded. Skip is dimmed/smaller.
 */
export default function VoteButtons({ disabled = true, onVote, voted = null }) {
  const baseBtn =
    'font-semibold rounded-lg transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-offset-bg-primary'

  const buttons = [
    {
      key: 'a',
      label: 'A is Better',
      className: `px-5 py-2.5 text-sm ${baseBtn} ${
        voted === 'a'
          ? 'bg-accent-info text-bg-primary ring-2 ring-accent-info'
          : disabled
            ? 'bg-bg-tertiary text-text-muted cursor-not-allowed'
            : 'bg-bg-tertiary text-text-primary hover:bg-accent-info/20 hover:text-accent-info border border-border-default hover:border-accent-info/40'
      }`,
    },
    {
      key: 'tie',
      label: 'Tie',
      className: `px-5 py-2.5 text-sm ${baseBtn} ${
        voted === 'tie'
          ? 'bg-accent-warning text-bg-primary ring-2 ring-accent-warning'
          : disabled
            ? 'bg-bg-tertiary text-text-muted cursor-not-allowed'
            : 'bg-bg-tertiary text-text-primary hover:bg-accent-warning/20 hover:text-accent-warning border border-border-default hover:border-accent-warning/40'
      }`,
    },
    {
      key: 'b',
      label: 'B is Better',
      className: `px-5 py-2.5 text-sm ${baseBtn} ${
        voted === 'b'
          ? 'bg-accent-info text-bg-primary ring-2 ring-accent-info'
          : disabled
            ? 'bg-bg-tertiary text-text-muted cursor-not-allowed'
            : 'bg-bg-tertiary text-text-primary hover:bg-accent-info/20 hover:text-accent-info border border-border-default hover:border-accent-info/40'
      }`,
    },
    {
      key: 'skip',
      label: 'Skip',
      className: `px-4 py-2 text-xs ${baseBtn} ${
        voted === 'skip'
          ? 'bg-text-muted/30 text-text-secondary ring-2 ring-text-muted'
          : disabled
            ? 'bg-bg-tertiary/50 text-text-muted/50 cursor-not-allowed'
            : 'bg-bg-tertiary/50 text-text-muted hover:bg-bg-hover hover:text-text-secondary border border-border-default/50 hover:border-border-default'
      }`,
    },
  ]

  return (
    <div className="flex items-center justify-center gap-3 py-4">
      {buttons.map((btn) => (
        <button
          key={btn.key}
          disabled={disabled || voted != null}
          onClick={() => onVote?.(btn.key)}
          className={btn.className}
        >
          {btn.label}
        </button>
      ))}
    </div>
  )
}

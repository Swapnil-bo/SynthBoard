import { useState } from 'react'
import ResponsePanel from '../components/arena/ResponsePanel'
import VoteButtons from '../components/arena/VoteButtons'
import useArena from '../hooks/useArena'

export default function ArenaPage() {
  const [prompt, setPrompt] = useState('')
  const {
    phase,
    battle,
    voteResult,
    error,
    voting,
    startBattle,
    submitVote,
    fetchRandomPrompt,
    reset,
  } = useArena()

  const [loadingPrompt, setLoadingPrompt] = useState(false)

  const handleRandomPrompt = async () => {
    setLoadingPrompt(true)
    const p = await fetchRandomPrompt()
    if (p) setPrompt(p)
    setLoadingPrompt(false)
  }

  const handleStart = () => {
    startBattle(prompt)
  }

  const handleNewBattle = () => {
    setPrompt('')
    reset()
  }

  const isLoading = phase === 'loading'
  const isBattleActive = phase !== 'idle' && phase !== 'error'
  const canVote = phase === 'voting'
  const isVoted = phase === 'voted'

  // Determine panel statuses based on phase
  const panelAStatus = (() => {
    if (phase === 'idle') return 'idle'
    if (phase === 'loading') return 'generating'
    return 'done'
  })()

  const panelBStatus = (() => {
    if (phase === 'idle') return 'idle'
    if (phase === 'loading') return 'waiting'
    if (phase === 'reveal_a') return 'generating'
    return 'done'
  })()

  // Show response text once the phase reaches reveal
  const showResponseA = battle && phase !== 'loading'
  const showResponseB = battle && !['loading', 'reveal_a'].includes(phase)

  // Elo changes after voting
  const eloChangeA = voteResult
    ? voteResult.model_a_elo_after - voteResult.model_a_elo_before
    : null
  const eloChangeB = voteResult
    ? voteResult.model_b_elo_after - voteResult.model_b_elo_before
    : null

  // Determine winner panels
  const winnerA = voteResult?.winner === 'a'
  const winnerB = voteResult?.winner === 'b'

  return (
    <div className="p-6 max-w-7xl mx-auto flex flex-col h-full">
      {/* Header */}
      <div className="mb-5">
        <h1 className="text-2xl font-semibold text-text-primary mb-1">Arena</h1>
        <p className="text-sm text-text-muted">
          Blind side-by-side battles. Vote for the better response. Elo ratings update after each vote.
        </p>
      </div>

      {/* Prompt input */}
      <div className="mb-5">
        <div className="flex gap-2 mb-2">
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Enter a prompt or use a random one..."
            disabled={isBattleActive}
            rows={3}
            className="flex-1 px-4 py-3 text-sm bg-bg-secondary border border-border-default rounded-lg text-text-primary placeholder-text-muted/60 resize-none focus:border-accent-info focus:outline-none disabled:opacity-50 font-mono"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && e.ctrlKey && !isBattleActive) {
                e.preventDefault()
                handleStart()
              }
            }}
          />
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleStart}
            disabled={isBattleActive}
            className="px-5 py-2 text-sm font-semibold rounded-lg bg-accent-success text-bg-primary hover:bg-accent-success/80 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? (
              <span className="flex items-center gap-2">
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Generating...
              </span>
            ) : (
              'Start Battle'
            )}
          </button>
          <button
            onClick={handleRandomPrompt}
            disabled={isBattleActive || loadingPrompt}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-bg-tertiary text-text-secondary border border-border-default hover:bg-bg-hover hover:text-text-primary disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {loadingPrompt ? '...' : 'Random Prompt'}
          </button>
          {isVoted && (
            <button
              onClick={handleNewBattle}
              className="px-4 py-2 text-sm font-medium rounded-lg bg-accent-info/15 text-accent-info hover:bg-accent-info/25 transition-colors ml-auto"
            >
              New Battle
            </button>
          )}
          {!isBattleActive && (
            <span className="text-xs text-text-muted ml-auto">Ctrl+Enter to start</span>
          )}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 px-4 py-3 rounded-lg bg-accent-error/10 border border-accent-error/30 text-accent-error text-sm">
          {error}
          <button onClick={reset} className="ml-3 text-xs opacity-60 hover:opacity-100 underline">
            Dismiss
          </button>
        </div>
      )}

      {/* Battle panels */}
      <div className="flex gap-4 flex-1 min-h-0 mb-2">
        <ResponsePanel
          label="Model A"
          status={panelAStatus}
          response={showResponseA ? battle.response_a : ''}
          ttftMs={showResponseA ? battle.model_a_ttft_ms : null}
          totalMs={showResponseA ? battle.model_a_total_ms : null}
          tokens={showResponseA ? battle.model_a_tokens : null}
          modelName={isVoted ? voteResult.model_a_name : null}
          eloChange={isVoted ? eloChangeA : null}
          winner={winnerA}
        />
        <ResponsePanel
          label="Model B"
          status={panelBStatus}
          response={showResponseB ? battle.response_b : ''}
          ttftMs={showResponseB ? battle.model_b_ttft_ms : null}
          totalMs={showResponseB ? battle.model_b_total_ms : null}
          tokens={showResponseB ? battle.model_b_tokens : null}
          modelName={isVoted ? voteResult.model_b_name : null}
          eloChange={isVoted ? eloChangeB : null}
          winner={winnerB}
        />
      </div>

      {/* Vote buttons */}
      <VoteButtons
        disabled={!canVote || voting}
        onVote={submitVote}
        voted={isVoted ? voteResult.winner : null}
      />

      {/* Loading hint */}
      {isLoading && (
        <p className="text-center text-xs text-text-muted animate-pulse">
          Running sequential inference... This may take a minute or two.
        </p>
      )}
    </div>
  )
}

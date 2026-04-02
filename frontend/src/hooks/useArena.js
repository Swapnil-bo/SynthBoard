import { useCallback, useRef, useState } from 'react'
import api from '../lib/api'

/**
 * Battle state machine:
 *
 *   idle → loading → reveal_a → reveal_b → voting → voted
 *                 ↘ error
 *
 * "loading"   — API call in flight (Panel A: Generating, Panel B: Waiting)
 * "reveal_a"  — Response A shown, Panel B switches to Generating
 * "reveal_b"  — Response B shown, vote buttons activate
 * "voting"    — Both shown, awaiting user vote
 * "voted"     — Vote submitted, model names + Elo changes revealed
 */
export default function useArena() {
  const [phase, setPhase] = useState('idle')
  const [battle, setBattle] = useState(null)   // BattleResponse from API
  const [voteResult, setVoteResult] = useState(null)  // VoteResponse from API
  const [error, setError] = useState(null)
  const [voting, setVoting] = useState(false)
  const timerRef = useRef(null)

  const reset = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    setPhase('idle')
    setBattle(null)
    setVoteResult(null)
    setError(null)
    setVoting(false)
  }, [])

  const startBattle = useCallback(async (prompt) => {
    if (timerRef.current) clearTimeout(timerRef.current)
    setPhase('loading')
    setBattle(null)
    setVoteResult(null)
    setError(null)

    try {
      const body = prompt?.trim() ? { prompt: prompt.trim() } : {}
      // Long timeout — sequential inference can take 240s+
      const { data } = await api.post('/arena/battle', body, { timeout: 300000 })
      setBattle(data)

      // Reveal A immediately
      setPhase('reveal_a')

      // After a delay, reveal B
      timerRef.current = setTimeout(() => {
        setPhase('reveal_b')
        // Short pause then enable voting
        timerRef.current = setTimeout(() => {
          setPhase('voting')
        }, 800)
      }, 1500)
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Battle failed'
      setError(msg)
      setPhase('error')
    }
  }, [])

  const submitVote = useCallback(async (winner) => {
    if (!battle?.id || voting) return
    setVoting(true)

    try {
      const { data } = await api.post(`/arena/battle/${battle.id}/vote`, { winner })
      setVoteResult(data)
      setPhase('voted')
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Vote failed'
      setError(msg)
    } finally {
      setVoting(false)
    }
  }, [battle, voting])

  const fetchRandomPrompt = useCallback(async () => {
    try {
      const { data } = await api.get('/arena/random-prompt')
      return data.prompt || ''
    } catch {
      return ''
    }
  }, [])

  return {
    phase,
    battle,
    voteResult,
    error,
    voting,
    startBattle,
    submitVote,
    fetchRandomPrompt,
    reset,
  }
}

import { useState, useEffect, useRef } from 'react'
import api from '../lib/api'

export default function useGpuStats(intervalMs = 5000) {
  const [stats, setStats] = useState(null)
  const [error, setError] = useState(null)
  const timerRef = useRef(null)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const { data } = await api.get('/system/gpu')
        if (!cancelled) {
          setStats(data)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to fetch GPU stats')
      }
    }

    poll()
    timerRef.current = setInterval(poll, intervalMs)

    return () => {
      cancelled = true
      clearInterval(timerRef.current)
    }
  }, [intervalMs])

  return { stats, error }
}

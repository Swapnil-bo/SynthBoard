import { useEffect, useRef, useState, useCallback } from "react";

/**
 * Server-Sent Events hook for training progress.
 *
 * Implements exponential backoff reconnect: 1s -> 2s -> 4s -> 8s -> 16s cap.
 * On successful connection, resets backoff to 1s.
 *
 * @param {string|null} url - SSE endpoint URL. Pass null to disable.
 * @param {object} options
 * @param {function} options.onProgress - Called with parsed data for "progress" events
 * @param {function} options.onCheckpoint - Called with parsed data for "checkpoint" events
 * @param {function} options.onComplete - Called with parsed data for "complete" events
 * @param {function} options.onError - Called with parsed data for "error" events
 * @param {function} options.onCancelled - Called with parsed data for "cancelled" events
 * @returns {{ connected: boolean, error: string|null, reconnecting: boolean }}
 */
export default function useSSE(url, options = {}) {
  const { onProgress, onCheckpoint, onComplete, onError, onCancelled } =
    options;

  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(null);
  const [reconnecting, setReconnecting] = useState(false);

  // Use refs for callbacks so we don't trigger re-connections on handler changes
  const callbacksRef = useRef({
    onProgress,
    onCheckpoint,
    onComplete,
    onError,
    onCancelled,
  });
  callbacksRef.current = {
    onProgress,
    onCheckpoint,
    onComplete,
    onError,
    onCancelled,
  };

  // Track if the stream has received a terminal event (complete/error/cancelled)
  const terminalRef = useRef(false);
  const eventSourceRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const backoffRef = useRef(1000); // Start at 1s

  const BACKOFF_CAP = 16000; // 16s max

  const cleanup = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!url) {
      cleanup();
      setConnected(false);
      setError(null);
      setReconnecting(false);
      terminalRef.current = false;
      backoffRef.current = 1000;
      return;
    }

    // Don't reconnect if we already received a terminal event
    if (terminalRef.current) {
      return;
    }

    function connect() {
      cleanup();

      const es = new EventSource(url);
      eventSourceRef.current = es;

      es.onopen = () => {
        setConnected(true);
        setError(null);
        setReconnecting(false);
        backoffRef.current = 1000; // Reset backoff on successful connection
      };

      // Handle named events
      es.addEventListener("progress", (e) => {
        try {
          const data = JSON.parse(e.data);
          callbacksRef.current.onProgress?.(data);
        } catch {}
      });

      es.addEventListener("checkpoint", (e) => {
        try {
          const data = JSON.parse(e.data);
          callbacksRef.current.onCheckpoint?.(data);
        } catch {}
      });

      es.addEventListener("complete", (e) => {
        try {
          const data = JSON.parse(e.data);
          callbacksRef.current.onComplete?.(data);
        } catch {}
        terminalRef.current = true;
        setConnected(false);
        cleanup();
      });

      es.addEventListener("error", (e) => {
        // This is the SSE "error" event type from our server, not a connection error
        if (e.data) {
          try {
            const data = JSON.parse(e.data);
            callbacksRef.current.onError?.(data);
            terminalRef.current = true;
            setConnected(false);
            cleanup();
            return;
          } catch {}
        }
      });

      es.addEventListener("cancelled", (e) => {
        try {
          const data = JSON.parse(e.data);
          callbacksRef.current.onCancelled?.(data);
        } catch {}
        terminalRef.current = true;
        setConnected(false);
        cleanup();
      });

      // Connection-level error (disconnect, network issue)
      es.onerror = () => {
        setConnected(false);

        // Don't reconnect if we got a terminal event
        if (terminalRef.current) {
          cleanup();
          return;
        }

        es.close();
        eventSourceRef.current = null;

        // Schedule reconnect with exponential backoff
        const delay = backoffRef.current;
        setReconnecting(true);
        setError(`Connection lost. Reconnecting in ${delay / 1000}s...`);

        reconnectTimerRef.current = setTimeout(() => {
          backoffRef.current = Math.min(
            backoffRef.current * 2,
            BACKOFF_CAP,
          );
          connect();
        }, delay);
      };
    }

    terminalRef.current = false;
    connect();

    return cleanup;
  }, [url, cleanup]);

  return { connected, error, reconnecting };
}

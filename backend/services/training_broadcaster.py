"""
SSE broadcast manager for training progress.

Bridges the synchronous training thread (TrainerCallback pushes events) with
the async SSE endpoints (multiple subscribers read events).

Uses a broadcast pattern: each connected SSE client gets its own bounded queue.
The TrainerCallback pushes events to ALL registered queues. If a queue is full
(slow client), old events are dropped via put_nowait with error handling.
"""
import json
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

QUEUE_MAX_SIZE = 100


@dataclass
class TrainingEvent:
    """A single event to send over SSE."""
    event_type: str  # "progress", "checkpoint", "complete", "error", "cancelled"
    data: dict = field(default_factory=dict)

    def to_sse(self) -> str:
        """Format as an SSE message string."""
        return f"event: {self.event_type}\ndata: {json.dumps(self.data)}\n\n"


class TrainingBroadcaster:
    """
    Manages SSE subscriber queues for a single training run.

    Thread-safe: the training thread calls push(), the async SSE endpoint
    iterates via subscribe()/unsubscribe().
    """

    def __init__(self, run_id: str):
        self.run_id = run_id
        self._subscribers: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._finished = False
        self._last_event: Optional[TrainingEvent] = None

    def subscribe(self) -> queue.Queue:
        """Register a new SSE subscriber. Returns the queue to read from."""
        q = queue.Queue(maxsize=QUEUE_MAX_SIZE)
        with self._lock:
            self._subscribers.append(q)
            # If training already finished, immediately push the last event
            # so a late-connecting client sees the final state
            if self._finished and self._last_event is not None:
                try:
                    q.put_nowait(self._last_event)
                except queue.Full:
                    pass
        logger.debug("SSE subscriber added for run %s (total: %d)",
                     self.run_id, len(self._subscribers))
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        """Remove a subscriber queue (called on client disconnect)."""
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass
        logger.debug("SSE subscriber removed for run %s (remaining: %d)",
                     self.run_id, len(self._subscribers))

    def push(self, event: TrainingEvent) -> None:
        """Push an event to all subscriber queues. Thread-safe."""
        with self._lock:
            if event.event_type in ("complete", "error", "cancelled"):
                self._finished = True
                self._last_event = event

            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except queue.Full:
                    # Slow client — drop oldest event and push new one
                    try:
                        q.get_nowait()
                        q.put_nowait(event)
                    except (queue.Empty, queue.Full):
                        pass

    @property
    def has_subscribers(self) -> bool:
        with self._lock:
            return len(self._subscribers) > 0

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)


# ── Global registry: run_id → broadcaster ──

_broadcasters: dict[str, TrainingBroadcaster] = {}
_registry_lock = threading.Lock()


def get_broadcaster(run_id: str) -> TrainingBroadcaster:
    """Get or create a broadcaster for a training run."""
    with _registry_lock:
        if run_id not in _broadcasters:
            _broadcasters[run_id] = TrainingBroadcaster(run_id)
        return _broadcasters[run_id]


def remove_broadcaster(run_id: str) -> None:
    """Remove a broadcaster when a training run is fully done and no subscribers remain."""
    with _registry_lock:
        _broadcasters.pop(run_id, None)

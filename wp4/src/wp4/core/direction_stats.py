"""Direction statistics dataclass for CAN gateway.

Encapsulates all per-direction statistics and state to reduce code duplication
in the gateway implementation.
"""

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Literal

Direction = Literal["0to1", "1to0"]


@dataclass
class DirectionStats:
    """Statistics and state for a single direction in the gateway.

    This dataclass encapsulates all per-direction data:
    - Message counters (received, forwarded, dropped)
    - Priority queue for delayed sending
    - Condition variable for sender thread coordination
    - Latency samples for monitoring
    - Enable flag for direction control

    Thread Safety:
    - Counter updates should be protected by external stats_lock
    - Queue operations should be protected by the condition
    - Latency samples should be protected by external latency_lock
    - Enable flag should be protected by external direction_lock

    Example:
        stats = DirectionStats(direction="0to1")
        with stats.condition:
            heapq.heappush(stats.queue, (send_time, recv_time, arb_id, data, ext))
            stats.condition.notify()
    """

    direction: Direction

    # Message counters
    received: int = 0
    forwarded: int = 0
    dropped: int = 0

    # Priority queue: (send_time, recv_time, arb_id, data, is_extended)
    queue: list[tuple[float, float, int, bytes, bool]] = field(default_factory=list)

    # Condition variable for sender thread coordination
    condition: threading.Condition = field(default_factory=threading.Condition)

    # Latency samples (microseconds)
    latency_samples: deque[float] = field(default_factory=lambda: deque(maxlen=100))

    # Direction enable flag
    enabled: bool = True

    def reset_counters(self) -> None:
        """Reset message counters to zero."""
        self.received = 0
        self.forwarded = 0
        self.dropped = 0

    def clear_queue(self) -> None:
        """Clear the message queue."""
        self.queue.clear()

    def clear_latency_samples(self) -> None:
        """Clear latency samples."""
        self.latency_samples.clear()

    def reset_all(self) -> None:
        """Reset all statistics and clear queues."""
        self.reset_counters()
        self.clear_queue()
        self.clear_latency_samples()

    @property
    def queue_size(self) -> int:
        """Get current queue size."""
        return len(self.queue)

    def get_latency_stats(self) -> dict[str, float | None]:
        """Calculate latency statistics from samples.

        Returns:
            Dictionary with min, max, avg, p95, p99 latency in microseconds,
            or None values if no samples available.
        """
        if not self.latency_samples:
            return {
                "min": None,
                "max": None,
                "avg": None,
                "p95": None,
                "p99": None,
            }

        samples = sorted(self.latency_samples)
        n = len(samples)

        return {
            "min": samples[0],
            "max": samples[-1],
            "avg": sum(samples) / n,
            "p95": samples[int(n * 0.95)] if n > 0 else None,
            "p99": samples[int(n * 0.99)] if n > 0 else None,
        }

    def to_dict(self) -> dict:
        """Convert statistics to dictionary for serialization.

        Returns:
            Dictionary with direction statistics (excludes thread objects).
        """
        return {
            "direction": self.direction,
            "received": self.received,
            "forwarded": self.forwarded,
            "dropped": self.dropped,
            "queue_size": self.queue_size,
            "enabled": self.enabled,
            "latency_stats": self.get_latency_stats(),
        }


def create_direction_pair() -> tuple[DirectionStats, DirectionStats]:
    """Create a pair of DirectionStats for bidirectional gateway.

    Returns:
        Tuple of (stats_0to1, stats_1to0)
    """
    return (
        DirectionStats(direction="0to1"),
        DirectionStats(direction="1to0"),
    )

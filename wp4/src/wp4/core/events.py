"""Framework-agnostic event system for decoupling components."""

import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class Direction(Enum):
    """Direction of CAN message flow.

    Preferred over magic strings like "0to1", "1to0", "both".
    Use Direction.ZERO_TO_ONE.value for string compatibility.
    """

    ZERO_TO_ONE = "0to1"
    ONE_TO_ZERO = "1to0"
    BOTH = "both"

    def __str__(self) -> str:
        """Return the string value for compatibility."""
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "Direction":
        """Convert string to Direction enum.

        Args:
            value: Direction string ("0to1", "1to0", or "both")

        Returns:
            Corresponding Direction enum value

        Raises:
            ValueError: If string doesn't match any direction
        """
        for member in cls:
            if member.value == value:
                return member
        msg = f"Invalid direction: {value}"
        raise ValueError(msg)


# Type alias for gradual migration from strings to enum
DirectionLike = Direction | str


# =============================================================================
# Typed Event Data Classes
# =============================================================================


@dataclass(frozen=True)
class GatewayStartedEvent:
    """Event data for GATEWAY_STARTED event.

    Attributes:
        iface0: First interface name
        iface1: Second interface name
        delay_ms: Configured delay in milliseconds
        loss_pct: Configured packet loss percentage
        jitter_ms: Configured jitter in milliseconds
    """

    iface0: str
    iface1: str
    delay_ms: int = 0
    loss_pct: float = 0.0
    jitter_ms: float = 0.0


@dataclass(frozen=True)
class GatewayStoppedEvent:
    """Event data for GATEWAY_STOPPED event.

    Attributes:
        iface0: First interface name
        iface1: Second interface name
    """

    iface0: str
    iface1: str


@dataclass(frozen=True)
class SettingsChangedEvent:
    """Event data for SETTINGS_CHANGED event.

    Attributes:
        delay_ms: New delay in milliseconds (or None if unchanged)
        loss_pct: New packet loss percentage (or None if unchanged)
        jitter_ms: New jitter in milliseconds (or None if unchanged)
    """

    delay_ms: int | None = None
    loss_pct: float | None = None
    jitter_ms: float | None = None


@dataclass(frozen=True)
class StatsUpdatedEvent:
    """Event data for STATS_UPDATED event.

    Attributes:
        direction: Direction of the statistics ("0to1" or "1to0")
        received: Number of messages received
        forwarded: Number of messages forwarded
        dropped: Number of messages dropped
        queue_size: Current queue size
    """

    direction: str
    received: int
    forwarded: int
    dropped: int
    queue_size: int


@dataclass(frozen=True)
class InterfaceStateChangedEvent:
    """Event data for INTERFACE_STATE_CHANGED event.

    Attributes:
        iface: Interface name
        state: Interface state ("UP", "DOWN", or error state)
        bitrate: Interface bitrate (if applicable)
        error: Error message (if any)
    """

    iface: str
    state: str
    bitrate: int | None = None
    error: str | None = None


# Type alias for any event data
EventData = (
    GatewayStartedEvent
    | GatewayStoppedEvent
    | SettingsChangedEvent
    | StatsUpdatedEvent
    | InterfaceStateChangedEvent
    | dict[str, Any]  # For backwards compatibility
    | None
)


class EventType(Enum):
    """Event types for gateway state changes."""

    GATEWAY_STARTED = "gateway_started"
    GATEWAY_STOPPED = "gateway_stopped"
    SETTINGS_CHANGED = "settings_changed"
    STATS_UPDATED = "stats_updated"
    INTERFACE_STATE_CHANGED = "interface_state_changed"


class EventBus:
    """Simple pub/sub event bus for decoupling components.

    Example:
        bus = EventBus()
        bus.subscribe(EventType.GATEWAY_STARTED, lambda data: print(f"Started: {data}"))
        bus.publish(EventType.GATEWAY_STARTED, {"iface0": "can0", "iface1": "can1"})
    """

    def __init__(self):
        self._listeners: dict[EventType, list[Callable[[Any], None]]] = {}

    def subscribe(self, event_type: EventType, callback: Callable[[Any], None]) -> None:
        """Subscribe to an event type.

        Args:
            event_type: The event type to subscribe to
            callback: Function to call when event is published, receives event data
        """
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(callback)

    def unsubscribe(self, event_type: EventType, callback: Callable[[Any], None]) -> None:
        """Unsubscribe from an event type.

        Args:
            event_type: The event type to unsubscribe from
            callback: The callback function to remove
        """
        if event_type in self._listeners:
            with contextlib.suppress(ValueError):
                self._listeners[event_type].remove(callback)

    def publish(self, event_type: EventType, data: Any = None) -> None:
        """Publish an event to all subscribers.

        Args:
            event_type: The event type to publish
            data: Optional data to pass to subscribers
        """
        for callback in self._listeners.get(event_type, []):
            # Don't let one subscriber's error break other subscribers
            try:
                callback(data)
            except Exception:
                logger.exception(
                    "Exception in event handler for %s (callback: %s)",
                    event_type.value,
                    callback.__name__ if hasattr(callback, "__name__") else repr(callback),
                )

    def clear(self) -> None:
        """Clear all subscribers."""
        self._listeners.clear()

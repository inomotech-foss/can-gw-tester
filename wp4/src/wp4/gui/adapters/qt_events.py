"""Qt event adapter - bridges EventBus to Qt signals."""

from typing import Any

from PySide6.QtCore import QObject, Signal

from wp4.core.events import EventBus, EventType


class QtEventAdapter(QObject):
    """Adapter that bridges EventBus events to Qt signals.

    This adapter subscribes to EventBus events and emits Qt signals,
    enabling thread-safe GUI updates while keeping the core layer
    Qt-independent.
    """

    # Qt signals for each event type
    gateway_started = Signal(object)  # GatewayStartedEvent data
    gateway_stopped = Signal()
    settings_changed = Signal(object)  # SettingsChangedEvent data
    stats_updated = Signal(object)  # StatsUpdatedEvent data
    interface_state_changed = Signal(str, object)  # interface name, state

    def __init__(self, event_bus: EventBus, parent: QObject | None = None):
        """Initialize Qt event adapter.

        Args:
            event_bus: EventBus to subscribe to
            parent: Optional parent QObject
        """
        super().__init__(parent)
        self._event_bus = event_bus

        # Subscribe to all event types
        self._event_bus.subscribe(EventType.GATEWAY_STARTED, self._on_gateway_started)
        self._event_bus.subscribe(EventType.GATEWAY_STOPPED, self._on_gateway_stopped)
        self._event_bus.subscribe(EventType.SETTINGS_CHANGED, self._on_settings_changed)
        self._event_bus.subscribe(EventType.STATS_UPDATED, self._on_stats_updated)
        self._event_bus.subscribe(
            EventType.INTERFACE_STATE_CHANGED, self._on_interface_state_changed
        )

    def _on_gateway_started(self, data: Any) -> None:
        """Handle GATEWAY_STARTED event."""
        self.gateway_started.emit(data)

    def _on_gateway_stopped(self, data: Any) -> None:
        """Handle GATEWAY_STOPPED event."""
        self.gateway_stopped.emit()

    def _on_settings_changed(self, data: Any) -> None:
        """Handle SETTINGS_CHANGED event."""
        self.settings_changed.emit(data)

    def _on_stats_updated(self, data: Any) -> None:
        """Handle STATS_UPDATED event."""
        self.stats_updated.emit(data)

    def _on_interface_state_changed(self, data: Any) -> None:
        """Handle INTERFACE_STATE_CHANGED event."""
        if data and "interface" in data:
            iface = data["interface"]
            state = data.get("state")
            self.interface_state_changed.emit(iface, state)

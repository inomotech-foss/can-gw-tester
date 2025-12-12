"""Gateway manager - wraps BidirectionalGateway with event publishing."""

from dataclasses import dataclass, field
from pathlib import Path

from wp4.core.events import EventBus, EventType
from wp4.core.gateway import BidirectionalGateway
from wp4.core.gateway_logger import GatewayLogger
from wp4.core.manipulation import ManipulationEngine, ManipulationRule


@dataclass
class GatewayConfig:
    """Configuration for a CAN gateway."""

    iface0: str
    iface1: str
    delay_ms: int = 0
    loss_pct: float = 0.0
    jitter_ms: float = 0.0
    enable_0to1: bool = True
    enable_1to0: bool = True
    log_path: str | None = field(default=None)  # Path for logging, None = disabled
    log_name: str | None = field(default=None)  # Custom log filename (without ext)


class GatewayManager:
    """Manages gateway lifecycle and publishes events.

    This class wraps BidirectionalGateway and prevents direct access to
    gateway internals. All state changes are published via EventBus.
    """

    def __init__(self, config: GatewayConfig, event_bus: EventBus):
        """Initialize gateway manager.

        Args:
            config: Gateway configuration
            event_bus: Event bus for publishing state changes
        """
        self._config = config
        self._event_bus = event_bus
        self._gateway: BidirectionalGateway | None = None
        self._logger = GatewayLogger(config.log_path)
        self._manipulator = ManipulationEngine()

    def start(self) -> None:
        """Start the gateway and publish GATEWAY_STARTED event."""
        if self._gateway is not None and self._gateway.is_running:
            return  # Already running

        # Start logger if path is configured
        if self._config.log_path:
            self._logger.set_log_path(self._config.log_path)
            self._logger.start(
                self._config.iface0,
                self._config.iface1,
                custom_name=self._config.log_name,
            )

        # Create and configure gateway
        self._gateway = BidirectionalGateway(
            iface0=self._config.iface0,
            iface1=self._config.iface1,
            delay_ms=self._config.delay_ms,
            loss_pct=self._config.loss_pct,
            jitter_ms=self._config.jitter_ms,
            logger=self._logger if self._config.log_path else None,
            manipulator=self._manipulator,
        )

        # Set direction enables
        self._gateway.set_direction_enabled("0to1", self._config.enable_0to1)
        self._gateway.set_direction_enabled("1to0", self._config.enable_1to0)

        # Start gateway
        self._gateway.start()

        # Publish event
        self._event_bus.publish(
            EventType.GATEWAY_STARTED,
            {
                "iface0": self._config.iface0,
                "iface1": self._config.iface1,
                "delay_ms": self._config.delay_ms,
                "loss_pct": self._config.loss_pct,
                "jitter_ms": self._config.jitter_ms,
            },
        )

    def stop(self) -> None:
        """Stop the gateway and publish GATEWAY_STOPPED event."""
        if self._gateway is None:
            return

        self._gateway.stop()
        self._gateway = None

        # Stop logger
        self._logger.stop()

        self._event_bus.publish(EventType.GATEWAY_STOPPED)

    def is_running(self) -> bool:
        """Check if gateway is running.

        Returns:
            True if gateway is running, False otherwise
        """
        return self._gateway is not None and self._gateway.is_running

    def update_settings(
        self,
        delay_ms: int | None = None,
        loss_pct: float | None = None,
        jitter_ms: float | None = None,
    ) -> None:
        """Update gateway settings and publish SETTINGS_CHANGED event.

        Args:
            delay_ms: New delay in milliseconds (None = no change)
            loss_pct: New packet loss percentage (None = no change)
            jitter_ms: New jitter in milliseconds (None = no change)
        """
        changed = {}

        if delay_ms is not None:
            self._config.delay_ms = delay_ms
            if self._gateway:
                self._gateway.delay_ms = delay_ms
            changed["delay_ms"] = delay_ms

        if loss_pct is not None:
            self._config.loss_pct = loss_pct
            if self._gateway:
                self._gateway.loss_pct = loss_pct
            changed["loss_pct"] = loss_pct

        if jitter_ms is not None:
            self._config.jitter_ms = jitter_ms
            if self._gateway:
                self._gateway.jitter_ms = jitter_ms
            changed["jitter_ms"] = jitter_ms

        if changed:
            self._event_bus.publish(EventType.SETTINGS_CHANGED, changed)

    def set_direction_enabled(self, direction: str, enabled: bool) -> None:
        """Enable or disable a specific direction.

        Args:
            direction: '0to1' or '1to0'
            enabled: True to enable, False to disable
        """
        if direction == "0to1":
            self._config.enable_0to1 = enabled
        elif direction == "1to0":
            self._config.enable_1to0 = enabled

        if self._gateway:
            self._gateway.set_direction_enabled(direction, enabled)

    def get_stats(self, direction: str) -> dict[str, int]:
        """Get statistics for a direction.

        Args:
            direction: '0to1' or '1to0'

        Returns:
            Dictionary with received, forwarded, dropped, queue_size
        """
        if self._gateway is None:
            return {
                "received": 0,
                "forwarded": 0,
                "dropped": 0,
                "queue_size": 0,
            }

        if direction == "0to1":
            return {
                "received": self._gateway.received_0to1,
                "forwarded": self._gateway.forwarded_0to1,
                "dropped": self._gateway.dropped_0to1,
                "queue_size": self._gateway.queue_size_0to1,
            }
        else:
            return {
                "received": self._gateway.received_1to0,
                "forwarded": self._gateway.forwarded_1to0,
                "dropped": self._gateway.dropped_1to0,
                "queue_size": self._gateway.queue_size_1to0,
            }

    def get_latency_samples(self, direction: str) -> list[float]:
        """Get latency samples for a direction.

        Args:
            direction: '0to1' or '1to0'

        Returns:
            List of latency samples in microseconds
        """
        if self._gateway is None:
            return []
        return self._gateway.get_latency_samples(direction)

    def clear_latency_samples(self) -> None:
        """Clear all latency samples."""
        if self._gateway:
            self._gateway.clear_latency_samples()

    def get_config(self) -> GatewayConfig:
        """Get current gateway configuration.

        Returns:
            Current configuration
        """
        return self._config

    def set_log_path(self, path: str | None, custom_name: str | None = None) -> None:
        """Set or disable logging path.

        If gateway is running, dynamically starts/stops the logger.

        Args:
            path: Directory path for log files, or None to disable logging
            custom_name: Optional custom filename (without extension)
        """
        self._config.log_path = path
        self._config.log_name = custom_name
        self._logger.set_log_path(path)

        # Dynamically start/stop logger if gateway is already running
        if self.is_running():
            if path:
                # Start logger with current interfaces
                self._logger.start(
                    self._config.iface0,
                    self._config.iface1,
                    custom_name=custom_name,
                )
                # Update gateway's logger reference
                if self._gateway:
                    self._gateway.set_logger(self._logger)
            else:
                # Stop logger and remove from gateway
                self._logger.stop()
                if self._gateway:
                    self._gateway.set_logger(None)

    def get_log_paths(self) -> dict[str, Path | None]:
        """Get current log file paths.

        Returns:
            Dictionary with '0to1' and '1to0' keys mapping to Path or None
        """
        return self._logger.get_log_paths()

    def is_logging_enabled(self) -> bool:
        """Check if logging is enabled.

        Returns:
            True if logging is enabled, False otherwise
        """
        return self._logger.is_enabled

    # Manipulation methods
    def add_manipulation_rule(self, rule: ManipulationRule) -> None:
        """Add a manipulation rule.

        Args:
            rule: Rule to add
        """
        self._manipulator.add_rule(rule)

    def remove_manipulation_rule(self, name: str) -> bool:
        """Remove a manipulation rule by name.

        Args:
            name: Name of the rule to remove

        Returns:
            True if rule was found and removed
        """
        return self._manipulator.remove_rule(name)

    def clear_manipulation_rules(self) -> None:
        """Remove all manipulation rules."""
        self._manipulator.clear_rules()

    def get_manipulation_rules(self) -> list[ManipulationRule]:
        """Get all manipulation rules.

        Returns:
            List of all rules
        """
        return self._manipulator.get_rules()

    def set_manipulation_rules(self, rules: list[ManipulationRule]) -> None:
        """Replace all manipulation rules.

        Args:
            rules: New list of rules
        """
        self._manipulator.set_rules(rules)

    def set_manipulation_enabled(self, enabled: bool) -> None:
        """Enable or disable manipulation.

        Args:
            enabled: True to enable, False to disable
        """
        self._manipulator.enabled = enabled

    def is_manipulation_enabled(self) -> bool:
        """Check if manipulation is enabled.

        Returns:
            True if manipulation is enabled
        """
        return self._manipulator.enabled

"""Gateway service - high-level facade for GUI."""

from dataclasses import dataclass
from pathlib import Path

from wp4.core.events import EventBus
from wp4.core.gateway_manager import GatewayConfig, GatewayManager
from wp4.core.interface_manager import InterfaceManager
from wp4.core.manipulation import ManipulationRule
from wp4.lib.canif import CanInterfaceState


@dataclass
class GatewayStatus:
    """Complete gateway status snapshot."""

    running: bool
    config: GatewayConfig
    stats_0to1: dict[str, int]
    stats_1to0: dict[str, int]
    interface_states: dict[str, CanInterfaceState | None]


class GatewayService:
    """High-level gateway service facade.

    This class provides a single entry point for GUI code to interact with
    the gateway. It coordinates between GatewayManager and InterfaceManager
    and provides a simplified API.
    """

    def __init__(self, config: GatewayConfig, event_bus: EventBus | None = None):
        """Initialize gateway service.

        Args:
            config: Gateway configuration
            event_bus: Optional event bus (creates new one if not provided)
        """
        self._config = config
        self._event_bus = event_bus or EventBus()

        # Create managers
        self._gateway_manager = GatewayManager(self._config, self._event_bus)
        self._interface_manager = InterfaceManager(self._config, self._event_bus)

    def start(self) -> None:
        """Start the gateway."""
        self._gateway_manager.start()

    def stop(self) -> None:
        """Stop the gateway."""
        self._gateway_manager.stop()

    def is_running(self) -> bool:
        """Check if gateway is running.

        Returns:
            True if gateway is running, False otherwise
        """
        return self._gateway_manager.is_running()

    def get_status(self) -> GatewayStatus:
        """Get complete gateway status.

        Returns:
            GatewayStatus with all current state
        """
        return GatewayStatus(
            running=self._gateway_manager.is_running(),
            config=self._gateway_manager.get_config(),
            stats_0to1=self._gateway_manager.get_stats("0to1"),
            stats_1to0=self._gateway_manager.get_stats("1to0"),
            interface_states=self._interface_manager.get_states(),
        )

    def update_settings(
        self,
        delay_ms: int | None = None,
        loss_pct: float | None = None,
        jitter_ms: float | None = None,
    ) -> None:
        """Update gateway settings.

        Args:
            delay_ms: New delay in milliseconds (None = no change)
            loss_pct: New packet loss percentage (None = no change)
            jitter_ms: New jitter in milliseconds (None = no change)
        """
        self._gateway_manager.update_settings(
            delay_ms=delay_ms, loss_pct=loss_pct, jitter_ms=jitter_ms
        )

    def enable_direction(self, direction: str) -> None:
        """Enable a specific direction.

        Args:
            direction: '0to1' or '1to0'
        """
        self._gateway_manager.set_direction_enabled(direction, True)

    def disable_direction(self, direction: str) -> None:
        """Disable a specific direction.

        Args:
            direction: '0to1' or '1to0'
        """
        self._gateway_manager.set_direction_enabled(direction, False)

    def set_direction_enabled(self, direction: str, enabled: bool) -> None:
        """Set direction enabled state.

        Args:
            direction: '0to1' or '1to0'
            enabled: True to enable, False to disable
        """
        self._gateway_manager.set_direction_enabled(direction, enabled)

    def bring_up_interface(self, iface: str) -> None:
        """Bring up a single CAN interface.

        Args:
            iface: Interface name to bring up
        """
        self._interface_manager.bring_up_interface(iface)

    def bring_up_interfaces(self) -> None:
        """Bring up both CAN interfaces."""
        self._interface_manager.bring_up_interfaces()

    def bring_down_interface(self, iface: str) -> None:
        """Bring down a single CAN interface.

        Args:
            iface: Interface name to bring down
        """
        self._interface_manager.bring_down_interface(iface)

    def bring_down_interfaces(self) -> None:
        """Bring down both CAN interfaces."""
        self._interface_manager.bring_down_interfaces()

    def get_interface_state(self, iface: str) -> CanInterfaceState | None:
        """Get state of a specific interface.

        Args:
            iface: Interface name

        Returns:
            Current interface state or None if error
        """
        return self._interface_manager.get_state(iface)

    def get_interface_states(self) -> dict[str, CanInterfaceState | None]:
        """Get states of all configured interfaces.

        Returns:
            Dictionary mapping interface names to their states
        """
        return self._interface_manager.get_states()

    def set_bitrate(self, bitrate: int) -> None:
        """Set bitrate for interface operations.

        Args:
            bitrate: Bitrate in bits per second (e.g., 500000 for 500kbps)
        """
        self._interface_manager.set_bitrate(bitrate)

    def get_bitrate(self) -> int:
        """Get current bitrate setting.

        Returns:
            Bitrate in bits per second
        """
        return self._interface_manager.get_bitrate()

    def get_latency_samples(self, direction: str) -> list[float]:
        """Get latency samples for a direction.

        Args:
            direction: '0to1' or '1to0'

        Returns:
            List of latency samples in microseconds
        """
        return self._gateway_manager.get_latency_samples(direction)

    def clear_latency_samples(self) -> None:
        """Clear all latency samples."""
        self._gateway_manager.clear_latency_samples()

    def get_gateway_manager(self) -> GatewayManager:
        """Get the underlying gateway manager.

        Returns:
            GatewayManager instance (for direct access if needed)
        """
        return self._gateway_manager

    def get_interface_manager(self) -> InterfaceManager:
        """Get the underlying interface manager.

        Returns:
            InterfaceManager instance (for direct access if needed)
        """
        return self._interface_manager

    def get_event_bus(self) -> EventBus:
        """Get the event bus.

        Returns:
            EventBus instance
        """
        return self._event_bus

    def get_config(self) -> GatewayConfig:
        """Get gateway configuration.

        Returns:
            Current configuration
        """
        return self._config

    def set_log_path(self, path: str | None, custom_name: str | None = None) -> None:
        """Set or disable logging path.

        Args:
            path: Directory path for log files, or None to disable logging
            custom_name: Optional custom filename (without extension)
        """
        self._gateway_manager.set_log_path(path, custom_name=custom_name)

    def get_log_paths(self) -> dict[str, Path | None]:
        """Get current log file paths.

        Returns:
            Dictionary with '0to1' and '1to0' keys mapping to Path or None
        """
        return self._gateway_manager.get_log_paths()

    def is_logging_enabled(self) -> bool:
        """Check if logging is enabled.

        Returns:
            True if logging is enabled, False otherwise
        """
        return self._gateway_manager.is_logging_enabled()

    # Manipulation methods
    def add_manipulation_rule(self, rule: ManipulationRule) -> None:
        """Add a manipulation rule.

        Args:
            rule: Rule to add
        """
        self._gateway_manager.add_manipulation_rule(rule)

    def remove_manipulation_rule(self, name: str) -> bool:
        """Remove a manipulation rule by name.

        Args:
            name: Name of the rule to remove

        Returns:
            True if rule was found and removed
        """
        return self._gateway_manager.remove_manipulation_rule(name)

    def clear_manipulation_rules(self) -> None:
        """Remove all manipulation rules."""
        self._gateway_manager.clear_manipulation_rules()

    def get_manipulation_rules(self) -> list[ManipulationRule]:
        """Get all manipulation rules.

        Returns:
            List of all rules
        """
        return self._gateway_manager.get_manipulation_rules()

    def set_manipulation_rules(self, rules: list[ManipulationRule]) -> None:
        """Replace all manipulation rules.

        Args:
            rules: New list of rules
        """
        self._gateway_manager.set_manipulation_rules(rules)

    def set_manipulation_enabled(self, enabled: bool) -> None:
        """Enable or disable manipulation.

        Args:
            enabled: True to enable, False to disable
        """
        self._gateway_manager.set_manipulation_enabled(enabled)

    def is_manipulation_enabled(self) -> bool:
        """Check if manipulation is enabled.

        Returns:
            True if manipulation is enabled
        """
        return self._gateway_manager.is_manipulation_enabled()

"""Interface manager - wraps CAN interface operations with event publishing."""

from wp4.core.events import EventBus, EventType
from wp4.core.gateway_manager import GatewayConfig
from wp4.lib.canif import (
    CanInterfaceState,
    get_interface_state,
    set_interface_down,
    set_interface_up,
)


class InterfaceManager:
    """Manages CAN interface state and publishes events.

    This class wraps lib.canif operations and prevents direct interface
    manipulation from GUI code. All state changes are published via EventBus.
    """

    def __init__(self, config: GatewayConfig, event_bus: EventBus):
        """Initialize interface manager.

        Args:
            config: Gateway configuration with interface names
            event_bus: Event bus for publishing state changes
        """
        self._config = config
        self._event_bus = event_bus
        self._bitrate = 500000  # Default bitrate

    def bring_up_interfaces(self) -> None:
        """Bring up both interfaces with configured bitrate.

        Publishes INTERFACE_STATE_CHANGED events for each interface.
        """
        # Bring up both interfaces
        for iface in [self._config.iface0, self._config.iface1]:
            try:
                set_interface_up(iface, self._bitrate)
                state = get_interface_state(iface)
                self._event_bus.publish(
                    EventType.INTERFACE_STATE_CHANGED,
                    {"interface": iface, "state": state},
                )
            except Exception as e:
                # Publish error state
                self._event_bus.publish(
                    EventType.INTERFACE_STATE_CHANGED,
                    {
                        "interface": iface,
                        "state": None,
                        "error": str(e),
                    },
                )

    def bring_down_interfaces(self) -> None:
        """Bring down both interfaces.

        Publishes INTERFACE_STATE_CHANGED events for each interface.
        """
        for iface in [self._config.iface0, self._config.iface1]:
            try:
                set_interface_down(iface)
                state = get_interface_state(iface)
                self._event_bus.publish(
                    EventType.INTERFACE_STATE_CHANGED,
                    {"interface": iface, "state": state},
                )
            except Exception as e:
                # Publish error state
                self._event_bus.publish(
                    EventType.INTERFACE_STATE_CHANGED,
                    {
                        "interface": iface,
                        "state": None,
                        "error": str(e),
                    },
                )

    def get_state(self, iface: str) -> CanInterfaceState | None:
        """Get current state of an interface.

        Args:
            iface: Interface name

        Returns:
            Current interface state or None if error
        """
        return get_interface_state(iface)

    def get_states(self) -> dict[str, CanInterfaceState | None]:
        """Get states of both configured interfaces.

        Returns:
            Dictionary mapping interface names to their states
        """
        return {
            self._config.iface0: get_interface_state(self._config.iface0),
            self._config.iface1: get_interface_state(self._config.iface1),
        }

    def set_bitrate(self, bitrate: int) -> None:
        """Set bitrate for future interface operations.

        Args:
            bitrate: Bitrate in bits per second (e.g., 500000 for 500kbps)
        """
        self._bitrate = bitrate

    def get_bitrate(self) -> int:
        """Get current bitrate setting.

        Returns:
            Bitrate in bits per second
        """
        return self._bitrate

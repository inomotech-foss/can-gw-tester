"""CAN Bus Factory for dependency injection.

Provides an abstraction for creating CAN Bus objects, allowing:
- Production code to use real SocketCAN interfaces
- Tests to inject mock bus objects
- Easy switching between real and virtual interfaces
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import can

if TYPE_CHECKING:
    from can import BusABC


class BusFactory(ABC):
    """Abstract factory for creating CAN Bus objects.

    Implement this interface to provide custom bus creation logic
    for testing or specialized configurations.
    """

    @abstractmethod
    def create_bus(
        self,
        channel: str,
        receive_own_messages: bool = False,
    ) -> "BusABC":
        """Create a CAN bus instance.

        Args:
            channel: Interface name (e.g., "vcan0", "can0")
            receive_own_messages: Whether to receive messages sent by this bus

        Returns:
            BusABC: CAN bus instance
        """
        ...


class SocketCANBusFactory(BusFactory):
    """Factory for creating SocketCAN bus instances.

    This is the default factory used in production.
    """

    def create_bus(
        self,
        channel: str,
        receive_own_messages: bool = False,
    ) -> "BusABC":
        """Create a SocketCAN bus instance.

        Args:
            channel: Interface name (e.g., "vcan0", "can0")
            receive_own_messages: Whether to receive messages sent by this bus

        Returns:
            BusABC: SocketCAN bus instance
        """
        return can.Bus(
            channel=channel,
            interface="socketcan",
            receive_own_messages=receive_own_messages,
        )


class MockBusFactory(BusFactory):
    """Factory for creating mock bus instances for testing.

    Allows injecting pre-created mock buses for unit testing
    without requiring real CAN interfaces.

    Example:
        ```python
        mock_bus0 = MagicMock(spec=can.BusABC)
        mock_bus1 = MagicMock(spec=can.BusABC)
        factory = MockBusFactory({"vcan0": mock_bus0, "vcan1": mock_bus1})
        gateway = BidirectionalGateway(..., bus_factory=factory)
        ```
    """

    def __init__(self, buses: dict[str, "BusABC"] | None = None):
        """Initialize mock bus factory.

        Args:
            buses: Dictionary mapping channel names to mock bus objects
        """
        self._buses = buses or {}

    def add_bus(self, channel: str, bus: "BusABC") -> None:
        """Add a mock bus for a channel.

        Args:
            channel: Interface name
            bus: Mock bus object to return for this channel
        """
        self._buses[channel] = bus

    def create_bus(
        self,
        channel: str,
        receive_own_messages: bool = False,
    ) -> "BusABC":
        """Get pre-configured mock bus for the channel.

        Args:
            channel: Interface name
            receive_own_messages: Ignored for mock buses

        Returns:
            BusABC: Mock bus instance

        Raises:
            KeyError: If no mock bus configured for this channel
        """
        if channel not in self._buses:
            raise KeyError(f"No mock bus configured for channel: {channel}")
        return self._buses[channel]


# Default factory instance for production use
_default_factory: BusFactory = SocketCANBusFactory()


def get_default_factory() -> BusFactory:
    """Get the default bus factory.

    Returns:
        BusFactory: Default factory instance (SocketCANBusFactory)
    """
    return _default_factory


def set_default_factory(factory: BusFactory) -> None:
    """Set the default bus factory.

    Use this for testing to inject a mock factory globally.

    Args:
        factory: New default factory instance
    """
    global _default_factory
    _default_factory = factory


def reset_default_factory() -> None:
    """Reset the default factory to SocketCANBusFactory."""
    global _default_factory
    _default_factory = SocketCANBusFactory()

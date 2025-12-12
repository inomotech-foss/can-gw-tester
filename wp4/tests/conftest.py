"""Shared pytest fixtures for WP4 test suite.

This module provides common fixtures used across all test modules,
reducing code duplication and ensuring consistent test setup.
"""

import subprocess

import pytest

from wp4.core.events import EventBus
from wp4.core.gateway import BidirectionalGateway
from wp4.core.gateway_manager import GatewayConfig
from wp4.services.gateway_service import GatewayService

# =============================================================================
# vCAN Interface Setup (Session-Scoped)
# =============================================================================


def _interface_exists(name: str) -> bool:
    """Check if a network interface exists."""
    result = subprocess.run(
        ["ip", "link", "show", name],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _interface_is_up(name: str) -> bool:
    """Check if a network interface is UP."""
    result = subprocess.run(
        ["ip", "link", "show", name],
        capture_output=True,
        text=True,
    )
    return "state UP" in result.stdout or "state UNKNOWN" in result.stdout


def _create_vcan_interface(name: str) -> bool:
    """Create a vcan interface if it doesn't exist."""
    if _interface_exists(name):
        return True

    # Load vcan kernel module if needed (use -n for non-interactive)
    subprocess.run(["sudo", "-n", "modprobe", "vcan"], capture_output=True)

    # Create the interface (use -n for non-interactive)
    result = subprocess.run(
        ["sudo", "-n", "ip", "link", "add", "dev", name, "type", "vcan"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 or _interface_exists(name)


def _bring_up_interface(name: str) -> bool:
    """Bring up a network interface."""
    if _interface_is_up(name):
        return True

    # Use -n for non-interactive sudo
    result = subprocess.run(
        ["sudo", "-n", "ip", "link", "set", name, "up"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _bring_down_interface(name: str) -> bool:
    """Bring down a network interface."""
    if not _interface_exists(name):
        return True

    # Use -n for non-interactive sudo
    result = subprocess.run(
        ["sudo", "-n", "ip", "link", "set", name, "down"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _ensure_vcan_up():
    """Helper to ensure vcan0 and vcan1 are created and UP.

    Called before each test that needs vcan interfaces.
    This does a down/up cycle to clear any pending messages in kernel buffers.
    """
    interfaces = ["vcan0", "vcan1"]

    for iface in interfaces:
        # Create interface if it doesn't exist
        if not _interface_exists(iface):
            _create_vcan_interface(iface)

        # Do a down/up cycle to clear kernel buffers from previous tests
        _bring_down_interface(iface)
        _bring_up_interface(iface)


@pytest.fixture(scope="session", autouse=True)
def ensure_vcan_interfaces():
    """Ensure vcan0 and vcan1 interfaces exist and are UP at session start.

    This session-scoped fixture runs once at the start of the test session.
    It creates and brings up vcan interfaces if they don't exist or are down.

    This is autouse=True, so it runs automatically for all tests.
    """
    _ensure_vcan_up()
    yield
    # Note: We don't tear down the interfaces after tests
    # as they might be used by other processes


@pytest.fixture
def vcan_up(ensure_vcan_interfaces):
    """Ensure vcan interfaces are UP before each test that needs them.

    Use this fixture for tests that create their own CAN buses or gateways
    without using the gateway fixtures. This runs before each test to ensure
    interfaces are up (in case previous tests brought them down).
    """
    _ensure_vcan_up()


# =============================================================================
# Gateway Fixtures
# =============================================================================


@pytest.fixture
def gateway(ensure_vcan_interfaces):
    """Create a gateway using vcan interfaces with no delay.

    Yields:
        BidirectionalGateway: Gateway instance with cleanup on teardown

    Example:
        def test_forwarding(gateway):
            gateway.start()
            # test logic
            # gateway.stop() is called automatically
    """
    # Ensure interfaces are up (may have been brought down by other tests)
    _ensure_vcan_up()

    gw = BidirectionalGateway(
        iface0="vcan0",
        iface1="vcan1",
        delay_ms=0,
        loss_pct=0.0,
        jitter_ms=0.0,
    )
    yield gw
    if gw.is_running:
        gw.stop()


@pytest.fixture
def gateway_with_delay(ensure_vcan_interfaces):
    """Create a gateway with 50ms delay for latency testing.

    Yields:
        BidirectionalGateway: Gateway instance with 50ms delay
    """
    _ensure_vcan_up()
    gw = BidirectionalGateway(
        iface0="vcan0",
        iface1="vcan1",
        delay_ms=50,
        loss_pct=0.0,
        jitter_ms=0.0,
    )
    yield gw
    if gw.is_running:
        gw.stop()


@pytest.fixture
def gateway_with_loss(ensure_vcan_interfaces):
    """Create a gateway with 50% packet loss for loss testing.

    Yields:
        BidirectionalGateway: Gateway instance with 50% loss
    """
    _ensure_vcan_up()
    gw = BidirectionalGateway(
        iface0="vcan0",
        iface1="vcan1",
        delay_ms=0,
        loss_pct=50.0,
        jitter_ms=0.0,
    )
    yield gw
    if gw.is_running:
        gw.stop()


@pytest.fixture
def gateway_with_jitter(ensure_vcan_interfaces):
    """Create a gateway with 10ms jitter for timing testing.

    Yields:
        BidirectionalGateway: Gateway instance with 10ms jitter
    """
    _ensure_vcan_up()
    gw = BidirectionalGateway(
        iface0="vcan0",
        iface1="vcan1",
        delay_ms=50,
        loss_pct=0.0,
        jitter_ms=10.0,
    )
    yield gw
    if gw.is_running:
        gw.stop()


# =============================================================================
# Configuration Fixtures
# =============================================================================


@pytest.fixture
def vcan_config():
    """Create a standard gateway configuration using vcan interfaces.

    Returns:
        GatewayConfig: Standard vcan configuration
    """
    return GatewayConfig(
        iface0="vcan0",
        iface1="vcan1",
        delay_ms=10,
        loss_pct=0.0,
        enable_0to1=True,
        enable_1to0=True,
    )


@pytest.fixture
def vcan_config_with_delay():
    """Create a gateway configuration with 50ms delay.

    Returns:
        GatewayConfig: Configuration with 50ms delay
    """
    return GatewayConfig(
        iface0="vcan0",
        iface1="vcan1",
        delay_ms=50,
        loss_pct=0.0,
        enable_0to1=True,
        enable_1to0=True,
    )


@pytest.fixture
def vcan_config_unidirectional():
    """Create a unidirectional gateway configuration (0to1 only).

    Returns:
        GatewayConfig: Configuration with only 0to1 enabled
    """
    return GatewayConfig(
        iface0="vcan0",
        iface1="vcan1",
        delay_ms=0,
        loss_pct=0.0,
        enable_0to1=True,
        enable_1to0=False,
    )


# =============================================================================
# Event System Fixtures
# =============================================================================


@pytest.fixture
def event_bus():
    """Create a fresh EventBus instance.

    Returns:
        EventBus: New event bus for pub/sub communication
    """
    return EventBus()


@pytest.fixture
def event_collector(event_bus):
    """Create an event collector that subscribes to all events.

    Args:
        event_bus: EventBus fixture

    Returns:
        dict: Dictionary mapping event types to lists of received events

    Example:
        def test_events(event_bus, event_collector):
            event_bus.publish(EventType.GATEWAY_STARTED, {"data": 1})
            assert len(event_collector[EventType.GATEWAY_STARTED]) == 1
    """
    from wp4.core.events import EventType

    collected: dict[EventType, list] = {et: [] for et in EventType}

    for event_type in EventType:
        event_bus.subscribe(event_type, lambda d, et=event_type: collected[et].append(d))

    return collected


# =============================================================================
# Service Fixtures
# =============================================================================


@pytest.fixture
def gateway_service(vcan_config, event_bus):
    """Create a GatewayService instance with vcan configuration.

    Args:
        vcan_config: GatewayConfig fixture
        event_bus: EventBus fixture

    Yields:
        GatewayService: Service instance with cleanup on teardown
    """
    service = GatewayService(vcan_config, event_bus)
    yield service
    if service.is_running():
        service.stop()


# =============================================================================
# File System Fixtures
# =============================================================================


@pytest.fixture
def temp_log_dir(tmp_path):
    """Create a temporary directory for log files.

    Args:
        tmp_path: pytest built-in tmp_path fixture

    Returns:
        Path: Temporary directory path for log files
    """
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    return log_dir


@pytest.fixture
def temp_export_dir(tmp_path):
    """Create a temporary directory for export files.

    Args:
        tmp_path: pytest built-in tmp_path fixture

    Returns:
        Path: Temporary directory path for export files
    """
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    return export_dir


# =============================================================================
# CAN Bus Fixtures
# =============================================================================


@pytest.fixture
def can_bus_pair():
    """Create a pair of CAN buses for vcan0 and vcan1.

    Yields:
        tuple: (bus0, bus1) - CAN bus instances for vcan0 and vcan1

    Example:
        def test_send_receive(can_bus_pair):
            bus0, bus1 = can_bus_pair
            bus0.send(can.Message(arbitration_id=0x123, data=b'\\x01'))
            msg = bus1.recv(timeout=1.0)
    """
    import can

    bus0 = can.Bus(channel="vcan0", interface="socketcan")
    bus1 = can.Bus(channel="vcan1", interface="socketcan")
    yield (bus0, bus1)
    bus0.shutdown()
    bus1.shutdown()


@pytest.fixture
def can_message_factory():
    """Factory fixture for creating CAN messages.

    Returns:
        callable: Factory function to create CAN messages

    Example:
        def test_messages(can_message_factory):
            msg = can_message_factory(0x123, [0x01, 0x02])
            assert msg.arbitration_id == 0x123
    """
    import can

    def factory(
        arb_id: int,
        data: list[int] | bytes | None = None,
        is_extended: bool = False,
    ) -> can.Message:
        """Create a CAN message.

        Args:
            arb_id: Arbitration ID
            data: Message data (list of ints or bytes)
            is_extended: Whether to use extended ID

        Returns:
            can.Message: CAN message instance
        """
        if data is None:
            data = []
        if isinstance(data, list):
            data = bytes(data)
        return can.Message(
            arbitration_id=arb_id,
            data=data,
            is_extended_id=is_extended,
        )

    return factory

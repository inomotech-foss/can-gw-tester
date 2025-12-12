"""Integration tests for InterfaceManager using vcan interfaces."""

import pytest

from wp4.core.events import EventBus, EventType
from wp4.core.gateway_manager import GatewayConfig
from wp4.core.interface_manager import InterfaceManager


@pytest.fixture
def event_bus():
    """Create a fresh EventBus for each test."""
    return EventBus()


@pytest.fixture
def config():
    """Create a test gateway configuration using vcan interfaces."""
    return GatewayConfig(
        iface0="vcan0",
        iface1="vcan1",
    )


def test_interface_manager_init(config, event_bus):
    """Test interface manager initialization."""
    manager = InterfaceManager(config, event_bus)
    assert manager.get_bitrate() == 500000  # Default bitrate


def test_interface_manager_bring_up_interfaces(config, event_bus):
    """Test bringing up interfaces."""
    manager = InterfaceManager(config, event_bus)
    events = []
    event_bus.subscribe(EventType.INTERFACE_STATE_CHANGED, lambda d: events.append(d))

    manager.bring_up_interfaces()

    # Should publish 2 events (one per interface)
    assert len(events) == 2

    # Check event data
    for event in events:
        assert event["interface"] in ["vcan0", "vcan1"]
        assert event["state"] is not None
        assert event["state"].state == "UP"


def test_interface_manager_bring_down_interfaces(config, event_bus):
    """Test bringing down interfaces."""
    manager = InterfaceManager(config, event_bus)
    events = []
    event_bus.subscribe(EventType.INTERFACE_STATE_CHANGED, lambda d: events.append(d))

    # Bring up first
    manager.bring_up_interfaces()
    events.clear()

    # Then bring down
    manager.bring_down_interfaces()

    # Should publish 2 events (one per interface)
    assert len(events) == 2

    # Check event data
    for event in events:
        assert event["interface"] in ["vcan0", "vcan1"]
        assert event["state"] is not None
        assert event["state"].state == "DOWN"


def test_interface_manager_get_state(config, event_bus):
    """Test getting state of a single interface."""
    manager = InterfaceManager(config, event_bus)

    # Bring interface up
    manager.bring_up_interfaces()

    # Get state
    state = manager.get_state("vcan0")
    assert state is not None
    assert state.name == "vcan0"
    assert state.state == "UP"

    # Bring interface down
    manager.bring_down_interfaces()

    # Get state again
    state = manager.get_state("vcan0")
    assert state is not None
    assert state.name == "vcan0"
    assert state.state == "DOWN"


def test_interface_manager_get_states(config, event_bus):
    """Test getting states of all configured interfaces."""
    manager = InterfaceManager(config, event_bus)

    manager.bring_up_interfaces()

    states = manager.get_states()

    assert "vcan0" in states
    assert "vcan1" in states
    assert states["vcan0"] is not None
    assert states["vcan1"] is not None
    assert states["vcan0"].state == "UP"
    assert states["vcan1"].state == "UP"

    manager.bring_down_interfaces()


def test_interface_manager_set_bitrate(config, event_bus):
    """Test setting bitrate."""
    manager = InterfaceManager(config, event_bus)

    manager.set_bitrate(250000)
    assert manager.get_bitrate() == 250000

    manager.set_bitrate(1000000)
    assert manager.get_bitrate() == 1000000


def test_interface_manager_get_state_nonexistent(config, event_bus):
    """Test getting state of non-existent interface."""
    manager = InterfaceManager(config, event_bus)

    state = manager.get_state("nonexistent999")
    assert state is None


def test_interface_manager_event_on_error(event_bus):
    """Test that error events are published when interface operations fail."""
    # Use non-existent interfaces to trigger errors
    config = GatewayConfig(iface0="nonexistent0", iface1="nonexistent1")
    manager = InterfaceManager(config, event_bus)

    events = []
    event_bus.subscribe(EventType.INTERFACE_STATE_CHANGED, lambda d: events.append(d))

    manager.bring_up_interfaces()

    # Should still publish events (with error information)
    assert len(events) == 2

    for event in events:
        assert event["interface"] in ["nonexistent0", "nonexistent1"]
        # State should be None and error should be present
        assert event["state"] is None
        assert "error" in event

"""Integration tests for GatewayService using vcan interfaces."""

import time

import pytest

from wp4.core.events import EventBus, EventType
from wp4.core.gateway_manager import GatewayConfig
from wp4.services.gateway_service import GatewayService


@pytest.fixture
def config():
    """Create a test gateway configuration using vcan interfaces."""
    return GatewayConfig(
        iface0="vcan0",
        iface1="vcan1",
        delay_ms=10,
        loss_pct=0.0,
        enable_0to1=True,
        enable_1to0=True,
    )


def test_gateway_service_init(config):
    """Test gateway service initialization."""
    service = GatewayService(config)
    assert not service.is_running()
    assert service.get_config() == config


def test_gateway_service_init_with_event_bus(config):
    """Test gateway service initialization with custom event bus."""
    event_bus = EventBus()
    service = GatewayService(config, event_bus)

    assert service.get_event_bus() is event_bus


def test_gateway_service_lifecycle(config):
    """Test service start and stop."""
    service = GatewayService(config)

    service.start()
    assert service.is_running()

    service.stop()
    assert not service.is_running()


def test_gateway_service_get_status(config):
    """Test getting complete gateway status."""
    service = GatewayService(config)

    status = service.get_status()

    assert not status.running
    assert status.config == config
    assert "received" in status.stats_0to1
    assert "received" in status.stats_1to0
    assert "vcan0" in status.interface_states
    assert "vcan1" in status.interface_states


def test_gateway_service_get_status_running(config):
    """Test getting status when gateway is running."""
    service = GatewayService(config)

    service.start()
    time.sleep(0.1)

    status = service.get_status()

    assert status.running
    assert status.stats_0to1["received"] >= 0
    assert status.stats_1to0["received"] >= 0

    service.stop()


def test_gateway_service_update_settings(config):
    """Test updating gateway settings."""
    service = GatewayService(config)

    service.update_settings(delay_ms=50, loss_pct=5.0)

    config = service.get_config()
    assert config.delay_ms == 50
    assert config.loss_pct == 5.0


def test_gateway_service_enable_disable_direction(config):
    """Test enabling and disabling directions."""
    service = GatewayService(config)

    service.disable_direction("0to1")
    assert not service.get_config().enable_0to1

    service.enable_direction("0to1")
    assert service.get_config().enable_0to1

    service.set_direction_enabled("1to0", False)
    assert not service.get_config().enable_1to0


def test_gateway_service_interface_operations(config):
    """Test interface management operations."""
    service = GatewayService(config)

    # Bring up interfaces
    service.bring_up_interfaces()

    states = service.get_interface_states()
    assert states["vcan0"] is not None
    assert states["vcan1"] is not None
    assert states["vcan0"].state == "UP"
    assert states["vcan1"].state == "UP"

    # Get individual interface state
    state = service.get_interface_state("vcan0")
    assert state is not None
    assert state.name == "vcan0"

    # Bring down interfaces
    service.bring_down_interfaces()

    states = service.get_interface_states()
    assert states["vcan0"] is not None
    assert states["vcan1"] is not None
    assert states["vcan0"].state == "DOWN"
    assert states["vcan1"].state == "DOWN"


def test_gateway_service_bitrate_operations(config):
    """Test bitrate get/set operations."""
    service = GatewayService(config)

    assert service.get_bitrate() == 500000  # Default

    service.set_bitrate(250000)
    assert service.get_bitrate() == 250000


def test_gateway_service_latency_operations(config):
    """Test latency sample operations."""
    service = GatewayService(config)

    service.start()
    time.sleep(0.1)

    # Should return list (may be empty if no traffic)
    samples_0to1 = service.get_latency_samples("0to1")
    samples_1to0 = service.get_latency_samples("1to0")
    assert isinstance(samples_0to1, list)
    assert isinstance(samples_1to0, list)

    # Clear samples
    service.clear_latency_samples()
    samples_0to1 = service.get_latency_samples("0to1")
    samples_1to0 = service.get_latency_samples("1to0")
    assert samples_0to1 == []
    assert samples_1to0 == []

    service.stop()


def test_gateway_service_get_managers(config):
    """Test getting underlying managers."""
    service = GatewayService(config)

    gateway_manager = service.get_gateway_manager()
    interface_manager = service.get_interface_manager()
    event_bus = service.get_event_bus()

    assert gateway_manager is not None
    assert interface_manager is not None
    assert event_bus is not None


def test_gateway_service_event_propagation(config):
    """Test that events from managers are propagated through event bus."""
    event_bus = EventBus()
    service = GatewayService(config, event_bus)

    started_events = []
    stopped_events = []
    event_bus.subscribe(EventType.GATEWAY_STARTED, lambda d: started_events.append(d))
    event_bus.subscribe(EventType.GATEWAY_STOPPED, lambda d: stopped_events.append(d))

    service.start()
    assert len(started_events) == 1

    service.stop()
    assert len(stopped_events) == 1


def test_gateway_service_full_workflow(config):
    """Test a complete workflow: interfaces up, start gateway, stop, interfaces down."""
    service = GatewayService(config)
    event_bus = service.get_event_bus()

    # Track all events
    all_events = []

    def event_tracker(event_type):
        def handler(data):
            all_events.append((event_type, data))

        return handler

    event_bus.subscribe(
        EventType.INTERFACE_STATE_CHANGED,
        event_tracker(EventType.INTERFACE_STATE_CHANGED),
    )
    event_bus.subscribe(EventType.GATEWAY_STARTED, event_tracker(EventType.GATEWAY_STARTED))
    event_bus.subscribe(EventType.GATEWAY_STOPPED, event_tracker(EventType.GATEWAY_STOPPED))

    # 1. Bring up interfaces
    service.bring_up_interfaces()

    # 2. Start gateway
    service.start()
    time.sleep(0.1)

    # 3. Update settings
    service.update_settings(delay_ms=20)

    # 4. Get status
    status = service.get_status()
    assert status.running
    assert status.config.delay_ms == 20

    # 5. Stop gateway
    service.stop()

    # 6. Bring down interfaces
    service.bring_down_interfaces()

    # Should have received events
    assert len(all_events) > 0

    # Check we got the expected event types
    event_types = [event[0] for event in all_events]
    assert EventType.INTERFACE_STATE_CHANGED in event_types
    assert EventType.GATEWAY_STARTED in event_types
    assert EventType.GATEWAY_STOPPED in event_types

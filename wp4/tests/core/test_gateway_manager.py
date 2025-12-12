"""Integration tests for GatewayManager using vcan interfaces."""

import time

import pytest

from wp4.core.events import EventBus, EventType
from wp4.core.gateway_manager import GatewayConfig, GatewayManager


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
        delay_ms=10,  # Small delay for faster tests
        loss_pct=0.0,  # No packet loss for predictable tests
        enable_0to1=True,
        enable_1to0=True,
    )


def test_gateway_manager_init(config, event_bus):
    """Test gateway manager initialization."""
    manager = GatewayManager(config, event_bus)
    assert not manager.is_running()
    assert manager.get_config() == config


def test_gateway_manager_lifecycle(config, event_bus):
    """Test gateway start and stop."""
    manager = GatewayManager(config, event_bus)

    started_events = []
    stopped_events = []
    event_bus.subscribe(EventType.GATEWAY_STARTED, lambda d: started_events.append(d))
    event_bus.subscribe(EventType.GATEWAY_STOPPED, lambda d: stopped_events.append(d))

    # Start gateway
    manager.start()
    assert manager.is_running()

    # Check GATEWAY_STARTED event
    assert len(started_events) == 1
    assert started_events[0]["iface0"] == "vcan0"
    assert started_events[0]["iface1"] == "vcan1"
    assert started_events[0]["delay_ms"] == 10
    assert started_events[0]["loss_pct"] == 0.0

    # Stop gateway
    manager.stop()
    assert not manager.is_running()

    # Check GATEWAY_STOPPED event
    assert len(stopped_events) == 1


def test_gateway_manager_start_idempotent(config, event_bus):
    """Test that starting an already running gateway is idempotent."""
    manager = GatewayManager(config, event_bus)
    events = []
    event_bus.subscribe(EventType.GATEWAY_STARTED, lambda d: events.append(d))

    manager.start()
    manager.start()  # Second start should do nothing

    # Should only publish one event
    assert len(events) == 1
    assert manager.is_running()

    manager.stop()


def test_gateway_manager_stop_when_not_running(config, event_bus):
    """Test stopping when gateway is not running."""
    manager = GatewayManager(config, event_bus)
    # Should not raise exception
    manager.stop()
    assert not manager.is_running()


def test_gateway_manager_update_settings(config, event_bus):
    """Test updating gateway settings."""
    manager = GatewayManager(config, event_bus)
    events = []
    event_bus.subscribe(EventType.SETTINGS_CHANGED, lambda d: events.append(d))

    # Update settings before starting
    manager.update_settings(delay_ms=50, loss_pct=5.0)

    assert manager.get_config().delay_ms == 50
    assert manager.get_config().loss_pct == 5.0

    assert len(events) == 1
    assert events[0]["delay_ms"] == 50
    assert events[0]["loss_pct"] == 5.0

    # Update settings while running
    manager.start()
    manager.update_settings(delay_ms=100)

    assert manager.get_config().delay_ms == 100
    assert len(events) == 2
    assert events[1] == {"delay_ms": 100}

    manager.stop()


def test_gateway_manager_update_settings_partial(config, event_bus):
    """Test updating only some settings."""
    manager = GatewayManager(config, event_bus)
    events = []
    event_bus.subscribe(EventType.SETTINGS_CHANGED, lambda d: events.append(d))

    manager.update_settings(delay_ms=30)

    assert manager.get_config().delay_ms == 30
    assert manager.get_config().loss_pct == 0.0  # Unchanged

    assert len(events) == 1
    assert events[0] == {"delay_ms": 30}


def test_gateway_manager_get_stats_not_running(config, event_bus):
    """Test getting stats when gateway is not running."""
    manager = GatewayManager(config, event_bus)

    stats = manager.get_stats("0to1")
    assert stats == {
        "received": 0,
        "forwarded": 0,
        "dropped": 0,
        "queue_size": 0,
    }


def test_gateway_manager_get_stats_running(config, event_bus):
    """Test getting stats when gateway is running."""
    manager = GatewayManager(config, event_bus)

    manager.start()
    time.sleep(0.1)  # Let gateway initialize

    # Get stats for both directions
    stats_0to1 = manager.get_stats("0to1")
    stats_1to0 = manager.get_stats("1to0")

    # Should have all keys
    assert "received" in stats_0to1
    assert "forwarded" in stats_0to1
    assert "dropped" in stats_0to1
    assert "queue_size" in stats_0to1

    assert "received" in stats_1to0
    assert "forwarded" in stats_1to0
    assert "dropped" in stats_1to0
    assert "queue_size" in stats_1to0

    # Initially should be zero (no traffic yet)
    assert stats_0to1["received"] == 0
    assert stats_1to0["received"] == 0

    manager.stop()


def test_gateway_manager_get_latency_samples(config, event_bus):
    """Test getting latency samples."""
    manager = GatewayManager(config, event_bus)

    # When not running, should return empty list
    samples = manager.get_latency_samples("0to1")
    assert samples == []

    manager.start()
    time.sleep(0.1)

    # Should return a list (may be empty if no traffic)
    samples = manager.get_latency_samples("0to1")
    assert isinstance(samples, list)

    manager.stop()


def test_gateway_manager_clear_latency_samples(config, event_bus):
    """Test clearing latency samples."""
    manager = GatewayManager(config, event_bus)

    manager.start()
    manager.clear_latency_samples()

    # After clearing, should be empty
    samples_0to1 = manager.get_latency_samples("0to1")
    samples_1to0 = manager.get_latency_samples("1to0")
    assert samples_0to1 == []
    assert samples_1to0 == []

    manager.stop()


def test_gateway_manager_set_direction_enabled(config, event_bus):
    """Test enabling/disabling directions."""
    manager = GatewayManager(config, event_bus)

    # Disable 0to1 direction
    manager.set_direction_enabled("0to1", False)
    assert not manager.get_config().enable_0to1
    assert manager.get_config().enable_1to0  # Other direction unchanged

    # Disable 1to0 direction
    manager.set_direction_enabled("1to0", False)
    assert not manager.get_config().enable_1to0

    # Re-enable both
    manager.set_direction_enabled("0to1", True)
    manager.set_direction_enabled("1to0", True)
    assert manager.get_config().enable_0to1
    assert manager.get_config().enable_1to0


def test_gateway_manager_get_config(config, event_bus):
    """Test getting gateway configuration."""
    manager = GatewayManager(config, event_bus)
    retrieved_config = manager.get_config()

    assert retrieved_config.iface0 == "vcan0"
    assert retrieved_config.iface1 == "vcan1"
    assert retrieved_config.delay_ms == 10
    assert retrieved_config.loss_pct == 0.0
    assert retrieved_config.enable_0to1 is True
    assert retrieved_config.enable_1to0 is True

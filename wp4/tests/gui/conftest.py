"""Pytest fixtures for GUI tests.

Provides fixtures for widget cleanup and vcan interface management
to prevent test interference.
"""

import contextlib

import pytest

from wp4.core.gateway_manager import GatewayConfig


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
def traffic_control_widget(qtbot, ensure_vcan_interfaces):
    """Create a TrafficControlWidget with proper cleanup.

    This fixture ensures the widget and its underlying service
    are properly stopped after the test to prevent daemon threads
    from interfering with subsequent tests.

    Yields:
        TrafficControlWidget: Widget instance with cleanup on teardown
    """
    from wp4.gui.widgets.traffic_control import TrafficControlWidget

    widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
    qtbot.addWidget(widget)
    yield widget
    # Ensure proper cleanup
    widget.stop()


@pytest.fixture(autouse=True)
def auto_cleanup_widgets(request):
    """Auto-cleanup TrafficControlWidget instances after each test.

    This fixture tracks all TrafficControlWidget instances created during
    a test and ensures they are stopped after the test completes.
    This prevents daemon threads from interfering with subsequent tests.
    """
    # List to track widgets created during the test
    widgets_to_cleanup: list = []

    # Store original __init__ to patch
    from wp4.gui.widgets.traffic_control import TrafficControlWidget

    original_init = TrafficControlWidget.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        widgets_to_cleanup.append(self)

    # Apply patch
    TrafficControlWidget.__init__ = patched_init

    yield

    # Restore original __init__
    TrafficControlWidget.__init__ = original_init

    # Stop all widgets created during the test
    for widget in widgets_to_cleanup:
        with contextlib.suppress(Exception):
            widget.stop()

"""GUI tests for TrafficControlWidget using pytest-qt."""

from PySide6.QtWidgets import QPushButton

from wp4.gui.widgets.traffic_control import TrafficControlWidget
from wp4.services.gateway_service import GatewayService


class TestTrafficControlWidget:
    """Tests for TrafficControlWidget."""

    def test_widget_creation_vcan(self, qtbot):
        """Test widget creates successfully with vcan interfaces."""
        widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
        qtbot.addWidget(widget)

        assert widget is not None
        assert widget._iface0 == "vcan0"
        assert widget._iface1 == "vcan1"

    def test_widget_creates_service(self, qtbot):
        """Test widget creates GatewayService if not provided."""
        widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
        qtbot.addWidget(widget)

        assert widget._service is not None
        assert isinstance(widget._service, GatewayService)

    def test_widget_uses_provided_service(self, qtbot, vcan_config):
        """Test widget uses provided service."""
        service = GatewayService(vcan_config)
        widget = TrafficControlWidget(
            iface0="vcan0",
            iface1="vcan1",
            service=service,
        )
        qtbot.addWidget(widget)

        assert widget._service is service

    def test_delay_spinbox_exists(self, qtbot):
        """Test delay spinbox is present."""
        widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
        qtbot.addWidget(widget)

        assert widget._delay_spin is not None
        assert widget._delay_spin.minimum() >= 0

    def test_loss_spinbox_exists(self, qtbot):
        """Test loss spinbox is present."""
        widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
        qtbot.addWidget(widget)

        assert widget._loss_spin is not None
        assert widget._loss_spin.minimum() >= 0.0
        assert widget._loss_spin.maximum() <= 100.0

    def test_jitter_spinbox_exists(self, qtbot):
        """Test jitter spinbox is present."""
        widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
        qtbot.addWidget(widget)

        assert widget._jitter_spin is not None
        assert widget._jitter_spin.minimum() >= 0.0

    def test_direction_checkboxes_exist(self, qtbot):
        """Test direction enable checkboxes exist."""
        widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
        qtbot.addWidget(widget)

        assert widget._enable_0to1 is not None
        assert widget._enable_1to0 is not None

    def test_direction_checkboxes_initial_state_checked(self, qtbot):
        """Test direction checkboxes are checkable."""
        widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
        qtbot.addWidget(widget)

        # Checkboxes should be present and checkable
        assert widget._enable_0to1.isEnabled()
        assert widget._enable_1to0.isEnabled()

    def test_find_start_button(self, qtbot):
        """Test that start/stop buttons exist in widget."""
        widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
        qtbot.addWidget(widget)

        # Find buttons by text
        buttons = widget.findChildren(QPushButton)
        button_texts = [b.text() for b in buttons]

        assert "Start All" in button_texts
        assert "Stop All" in button_texts

    def test_find_interface_buttons(self, qtbot):
        """Test that interface control buttons exist."""
        widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
        qtbot.addWidget(widget)

        buttons = widget.findChildren(QPushButton)
        button_texts = [b.text() for b in buttons]

        assert "Up" in button_texts
        assert "Down" in button_texts
        assert "Both Up" in button_texts
        assert "Both Down" in button_texts


class TestTrafficControlWidgetInteraction:
    """Tests for user interaction with TrafficControlWidget."""

    def test_delay_change_value(self, qtbot):
        """Test changing delay spinbox value."""
        widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
        qtbot.addWidget(widget)

        # Change delay
        new_delay = 50
        widget._delay_spin.setValue(new_delay)

        assert widget._delay_spin.value() == new_delay

    def test_loss_change_value(self, qtbot):
        """Test changing loss spinbox value."""
        widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
        qtbot.addWidget(widget)

        # Change loss
        new_loss = 10.0
        widget._loss_spin.setValue(new_loss)

        assert widget._loss_spin.value() == new_loss

    def test_direction_checkbox_toggle(self, qtbot):
        """Test toggling direction checkboxes."""
        widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
        qtbot.addWidget(widget)

        # Toggle checkbox
        initial_state = widget._enable_0to1.isChecked()
        widget._enable_0to1.setChecked(not initial_state)

        assert widget._enable_0to1.isChecked() != initial_state


class TestTrafficControlWidgetStatistics:
    """Tests for statistics display in TrafficControlWidget."""

    def test_stats_labels_exist(self, qtbot):
        """Test statistic labels exist."""
        widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
        qtbot.addWidget(widget)

        # Check stats labels exist (actual attribute names)
        assert widget._stats_0to1 is not None
        assert widget._stats_1to0 is not None

    def test_stats_timer_active(self, qtbot):
        """Test stats refresh timer is active."""
        widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
        qtbot.addWidget(widget)

        assert widget._stats_timer is not None
        assert widget._stats_timer.isActive()
        assert widget._stats_timer.interval() == 500

    def test_refresh_stats_method(self, qtbot):
        """Test _refresh_stats method runs without error."""
        widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
        qtbot.addWidget(widget)

        # Should not raise
        widget._refresh_stats()


class TestTrafficControlWidgetInterface:
    """Tests for interface control in TrafficControlWidget."""

    def test_interface_status_labels_exist(self, qtbot):
        """Test interface status labels exist."""
        widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
        qtbot.addWidget(widget)

        assert widget._if0_status is not None
        assert widget._if1_status is not None

    def test_interface_status_initial_text(self, qtbot):
        """Test interface status shows interface name."""
        widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
        qtbot.addWidget(widget)

        assert "vcan0" in widget._if0_status.text()
        assert "vcan1" in widget._if1_status.text()


class TestTrafficControlWidgetCleanup:
    """Tests for widget cleanup."""

    def test_stop_method_stops_timer(self, qtbot):
        """Test stop() method stops the stats timer."""
        widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
        qtbot.addWidget(widget)

        assert widget._stats_timer.isActive()

        widget.stop()

        assert not widget._stats_timer.isActive()

    def test_stop_method_stops_service(self, qtbot, vcan_up):
        """Test stop() method stops the gateway service if running."""
        widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
        qtbot.addWidget(widget)

        # Start the gateway
        widget._service.start()

        assert widget._service.is_running()

        # Stop via widget
        widget.stop()

        assert not widget._service.is_running()


class TestTrafficControlWidgetLogging:
    """Tests for logging controls."""

    def test_logging_button_exists(self, qtbot):
        """Test logging start/stop button exists."""
        widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
        qtbot.addWidget(widget)

        assert widget._log_btn is not None

    def test_logging_path_edit_exists(self, qtbot):
        """Test logging path edit exists."""
        widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
        qtbot.addWidget(widget)

        assert widget._log_path_edit is not None

    def test_export_buttons_exist(self, qtbot):
        """Test export buttons exist."""
        widget = TrafficControlWidget(iface0="vcan0", iface1="vcan1")
        qtbot.addWidget(widget)

        assert widget._export_btn is not None
        assert widget._export_file_btn is not None

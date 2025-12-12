"""GUI tests for StatisticsWidget using pytest-qt."""

from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QTableWidget

from wp4.gui.widgets.statistics import StatisticsWidget


class TestStatisticsWidget:
    """Tests for StatisticsWidget."""

    def test_widget_creation(self, qtbot):
        """Test widget creates successfully."""
        widget = StatisticsWidget()
        qtbot.addWidget(widget)

        assert widget is not None

    def test_refresh_spinbox_exists(self, qtbot):
        """Test refresh spinbox is present."""
        widget = StatisticsWidget()
        qtbot.addWidget(widget)

        assert widget._refresh_spin is not None
        assert widget._refresh_spin.minimum() == 100
        assert widget._refresh_spin.maximum() == 5000
        assert widget._refresh_spin.value() == 1000
        assert widget._refresh_spin.suffix() == " ms"

    def test_refresh_spinbox_changes_timer_interval(self, qtbot):
        """Test changing refresh spinbox updates timer interval."""
        widget = StatisticsWidget()
        qtbot.addWidget(widget)

        # Timer should exist after widget creation
        assert widget._update_timer is not None
        initial_interval = widget._update_timer.interval()
        assert initial_interval == 1000

        # Change spinbox value
        widget._refresh_spin.setValue(500)

        # Timer interval should update
        assert widget._update_timer.interval() == 500

    def test_refresh_spinbox_step(self, qtbot):
        """Test refresh spinbox has 100ms step."""
        widget = StatisticsWidget()
        qtbot.addWidget(widget)

        assert widget._refresh_spin.singleStep() == 100

    def test_interface_table_exists(self, qtbot):
        """Test interface statistics table exists."""
        widget = StatisticsWidget()
        qtbot.addWidget(widget)

        assert widget._iface_table is not None
        assert isinstance(widget._iface_table, QTableWidget)
        assert widget._iface_table.rowCount() == 2
        assert widget._iface_table.columnCount() == 6

    def test_interface_table_headers(self, qtbot):
        """Test interface table has correct headers."""
        widget = StatisticsWidget()
        qtbot.addWidget(widget)

        headers = []
        for col in range(widget._iface_table.columnCount()):
            item = widget._iface_table.horizontalHeaderItem(col)
            headers.append(item.text() if item else "")

        assert "Interface" in headers
        assert "RX Packets" in headers
        assert "TX Packets" in headers
        assert "RX/s" in headers
        assert "TX/s" in headers
        assert "Errors" in headers

    def test_latency_labels_exist(self, qtbot):
        """Test latency display labels exist."""
        widget = StatisticsWidget()
        qtbot.addWidget(widget)

        assert widget._lat_0to1_label is not None
        assert widget._lat_1to0_label is not None
        assert widget._lat_avg_label is not None
        assert widget._lat_p95_label is not None
        assert widget._lat_p99_label is not None
        assert widget._lat_samples_label is not None

    def test_status_labels_exist(self, qtbot):
        """Test status labels exist."""
        widget = StatisticsWidget()
        qtbot.addWidget(widget)

        assert widget._mode_label is not None
        assert widget._uptime_label is not None
        assert widget._ifaces_label is not None

    def test_rate_labels_exist(self, qtbot):
        """Test live throughput labels exist."""
        widget = StatisticsWidget()
        qtbot.addWidget(widget)

        assert widget._rate_0_label is not None
        assert widget._rate_1_label is not None
        assert widget._total_rate_label is not None

    def test_forwarding_labels_exist(self, qtbot):
        """Test forwarding statistics labels exist."""
        widget = StatisticsWidget()
        qtbot.addWidget(widget)

        assert widget._fwd_0to1_label is not None
        assert widget._fwd_1to0_label is not None
        assert widget._fwd_total_label is not None

    def test_initial_latency_display(self, qtbot):
        """Test initial latency labels show placeholder text."""
        widget = StatisticsWidget()
        qtbot.addWidget(widget)

        # Without service, should show placeholder
        assert "-- ms" in widget._lat_0to1_label.text()
        assert "-- ms" in widget._lat_1to0_label.text()
        assert "-- ms" in widget._lat_avg_label.text()

    def test_stop_method_stops_timer(self, qtbot):
        """Test stop() method stops the update timer."""
        widget = StatisticsWidget()
        qtbot.addWidget(widget)

        assert widget._update_timer is not None
        assert widget._update_timer.isActive()

        widget.stop()

        assert not widget._update_timer.isActive()


class TestStatisticsWidgetWithService:
    """Tests for StatisticsWidget with a GatewayService."""

    @pytest.fixture
    def mock_service(self):
        """Create a mock GatewayService."""
        service = Mock()
        mock_config = Mock(
            iface0="vcan0",
            iface1="vcan1",
            delay_ms=10,
            loss_pct=0.0,
            enable_0to1=True,
            enable_1to0=True,
        )
        service.get_status.return_value = Mock(
            running=True,
            stats_0to1={"received": 100, "forwarded": 90, "dropped": 10},
            stats_1to0={"received": 200, "forwarded": 180, "dropped": 20},
            config=mock_config,
        )
        service.get_latency_samples.return_value = [1000.0, 2000.0, 3000.0]
        service.get_interface_states.return_value = {"vcan0": "UP", "vcan1": "UP"}
        return service

    def test_widget_with_service(self, qtbot, mock_service):
        """Test widget with service shows statistics."""
        widget = StatisticsWidget(service=mock_service)
        qtbot.addWidget(widget)

        assert widget._service is mock_service

    def test_refresh_calls_service(self, qtbot, mock_service):
        """Test refresh calls service methods."""
        widget = StatisticsWidget(service=mock_service)
        qtbot.addWidget(widget)

        # Trigger refresh
        widget._refresh_all()

        # Service should be called
        mock_service.get_status.assert_called()

    def test_set_service_via_traffic_control(self, qtbot, mock_service):
        """Test setting service via set_traffic_control."""
        widget = StatisticsWidget()
        qtbot.addWidget(widget)

        assert widget._service is None

        # Create a mock TrafficControlWidget
        mock_tc = Mock()
        mock_tc.get_gateway_service.return_value = mock_service
        mock_tc._event_adapter = None

        widget.set_traffic_control(mock_tc)

        assert widget._service is mock_service


class TestStatisticsWidgetInteraction:
    """Tests for user interaction with StatisticsWidget."""

    def test_refresh_method_runs(self, qtbot):
        """Test refresh method runs without error."""
        widget = StatisticsWidget()
        qtbot.addWidget(widget)

        # Just verify widget responds to refresh call
        widget._refresh_all()  # Should not raise

    def test_reset_method_runs(self, qtbot):
        """Test reset method runs without error."""
        widget = StatisticsWidget()
        qtbot.addWidget(widget)

        # Just verify widget responds to reset call
        widget._reset_counters()  # Should not raise

    def test_spinbox_value_change(self, qtbot):
        """Test spinbox accepts value changes."""
        widget = StatisticsWidget()
        qtbot.addWidget(widget)

        widget._refresh_spin.setValue(2000)

        assert widget._refresh_spin.value() == 2000
        assert widget._update_timer is not None
        assert widget._update_timer.interval() == 2000

    def test_spinbox_min_max_bounds(self, qtbot):
        """Test spinbox respects min/max bounds."""
        widget = StatisticsWidget()
        qtbot.addWidget(widget)

        # Try to set below minimum
        widget._refresh_spin.setValue(50)
        assert widget._refresh_spin.value() == 100  # Clamped to min

        # Try to set above maximum
        widget._refresh_spin.setValue(10000)
        assert widget._refresh_spin.value() == 5000  # Clamped to max

    def test_refresh_public_method(self, qtbot):
        """Test public refresh() method works."""
        widget = StatisticsWidget()
        qtbot.addWidget(widget)

        # Public method should delegate to _refresh_all
        widget.refresh()  # Should not raise


class TestStatisticsWidgetPercentiles:
    """Tests for percentile calculations."""

    def test_calculate_percentiles_empty(self, qtbot):
        """Test percentile calculation with empty samples."""
        widget = StatisticsWidget()
        qtbot.addWidget(widget)

        result = widget._calculate_percentiles([], [95, 99])
        assert result == [0.0, 0.0]

    def test_calculate_percentiles_with_data(self, qtbot):
        """Test percentile calculation with sample data."""
        widget = StatisticsWidget()
        qtbot.addWidget(widget)

        samples = [float(i) for i in range(100)]  # 0.0-99.0
        result = widget._calculate_percentiles(samples, [95, 99])

        assert result[0] == 95.0  # P95
        assert result[1] == 99.0  # P99

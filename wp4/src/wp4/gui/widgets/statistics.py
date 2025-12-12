"""Statistics widget for live interface and latency statistics.

Latency is measured directly in the BidirectionalGateway (recv_time to send_time).
"""

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from wp4.gui.adapters.qt_events import QtEventAdapter
from wp4.services.gateway_service import GatewayService


class StatisticsWidget(QWidget):
    """Widget displaying live interface and latency statistics.

    Uses GatewayService for all statistics access, eliminating direct
    coupling to TrafficControlWidget.
    """

    def __init__(
        self,
        iface0: str = "can0",
        iface1: str = "can1",
        service: GatewayService | None = None,
        event_adapter: QtEventAdapter | None = None,
    ):
        super().__init__()
        self._iface0 = iface0
        self._iface1 = iface1
        self._start_time = time.time()
        self._prev_stats = {}
        self._update_timer: QTimer | None = None

        # Service for accessing gateway state
        self._service = service
        self._event_adapter = event_adapter

        # Connect to settings changed event to clear latency samples
        if self._event_adapter:
            self._event_adapter.settings_changed.connect(self._on_settings_changed)

        self._setup_ui()
        self._start_live_updates()

    def set_traffic_control(self, tc):
        """Set reference to TrafficControlWidget (backwards compatibility).

        This method is kept for backwards compatibility with MainWindow,
        but now extracts the service from the widget instead of using
        the widget directly.
        """
        if tc:
            self._service = tc.get_gateway_service()
            self._event_adapter = tc._event_adapter

            # Connect to settings changed event
            if self._event_adapter:
                self._event_adapter.settings_changed.connect(self._on_settings_changed)

    def _on_settings_changed(self, data):
        """Called when settings change - clear latency samples if delay changed."""
        if "delay_ms" in data and self._service:
            self._service.clear_latency_samples()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Gateway Status
        status_group = QGroupBox("Status")
        status_layout = QGridLayout(status_group)

        status_layout.addWidget(QLabel("Mode:"), 0, 0)
        self._mode_label = QLabel("--")
        self._mode_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(self._mode_label, 0, 1)

        status_layout.addWidget(QLabel("Interfaces:"), 1, 0)
        self._ifaces_label = QLabel(f"{self._iface0} <-> {self._iface1}")
        self._ifaces_label.setStyleSheet("font-weight: bold; color: #00aaff;")
        status_layout.addWidget(self._ifaces_label, 1, 1)

        status_layout.addWidget(QLabel("Uptime:"), 2, 0)
        self._uptime_label = QLabel("0s")
        status_layout.addWidget(self._uptime_label, 2, 1)

        layout.addWidget(status_group)

        # Interface Statistics
        iface_group = QGroupBox("Interface Statistics")
        iface_layout = QVBoxLayout(iface_group)

        self._iface_table = QTableWidget(2, 6)
        self._iface_table.setHorizontalHeaderLabels(
            ["Interface", "RX Packets", "TX Packets", "RX/s", "TX/s", "Errors"]
        )
        self._iface_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._iface_table.verticalHeader().setVisible(False)
        self._iface_table.setMaximumHeight(90)

        self._iface_table.setItem(0, 0, QTableWidgetItem(self._iface0))
        self._iface_table.setItem(1, 0, QTableWidgetItem(self._iface1))
        for row in range(2):
            for col in range(1, 6):
                self._iface_table.setItem(row, col, QTableWidgetItem("0"))

        iface_layout.addWidget(self._iface_table)
        layout.addWidget(iface_group)

        # Live Throughput
        rates_group = QGroupBox("Live Throughput")
        rates_layout = QGridLayout(rates_group)

        rates_layout.addWidget(QLabel(f"{self._iface0} RX:"), 0, 0)
        self._rate_0_label = QLabel("0 msg/s")
        self._rate_0_label.setStyleSheet("font-weight: bold; color: #44aa44;")
        rates_layout.addWidget(self._rate_0_label, 0, 1)

        rates_layout.addWidget(QLabel(f"{self._iface1} RX:"), 1, 0)
        self._rate_1_label = QLabel("0 msg/s")
        self._rate_1_label.setStyleSheet("font-weight: bold; color: #44aa44;")
        rates_layout.addWidget(self._rate_1_label, 1, 1)

        rates_layout.addWidget(QLabel("Total:"), 2, 0)
        self._total_rate_label = QLabel("0 msg/s")
        self._total_rate_label.setStyleSheet("font-weight: bold; font-size: 14pt; color: #00aaff;")
        rates_layout.addWidget(self._total_rate_label, 2, 1)

        layout.addWidget(rates_group)

        # Forwarding Statistics
        fwd_group = QGroupBox("Forwarding")
        fwd_layout = QGridLayout(fwd_group)

        fwd_layout.addWidget(QLabel(f"{self._iface0} → {self._iface1}:"), 0, 0)
        self._fwd_0to1_label = QLabel("--")
        self._fwd_0to1_label.setStyleSheet("font-family: monospace;")
        fwd_layout.addWidget(self._fwd_0to1_label, 0, 1)

        fwd_layout.addWidget(QLabel(f"{self._iface1} → {self._iface0}:"), 1, 0)
        self._fwd_1to0_label = QLabel("--")
        self._fwd_1to0_label.setStyleSheet("font-family: monospace;")
        fwd_layout.addWidget(self._fwd_1to0_label, 1, 1)

        # Total forwarded
        fwd_layout.addWidget(QLabel("Total FWD:"), 2, 0)
        self._fwd_total_label = QLabel("0")
        self._fwd_total_label.setStyleSheet("font-weight: bold; font-size: 14pt; color: #00aaff;")
        fwd_layout.addWidget(self._fwd_total_label, 2, 1)

        layout.addWidget(fwd_group)

        # Latency Measurement
        latency_group = QGroupBox("Live Latency")
        latency_layout = QVBoxLayout(latency_group)

        # Direction 0 -> 1
        dir1_layout = QGridLayout()
        dir1_layout.addWidget(QLabel(f"{self._iface0} → {self._iface1}:"), 0, 0)
        self._lat_0to1_label = QLabel("-- ms")
        self._lat_0to1_label.setStyleSheet("font-weight: bold; color: #44aa44;")
        dir1_layout.addWidget(self._lat_0to1_label, 0, 1)
        latency_layout.addLayout(dir1_layout)

        # Direction 1 -> 0
        dir2_layout = QGridLayout()
        dir2_layout.addWidget(QLabel(f"{self._iface1} → {self._iface0}:"), 0, 0)
        self._lat_1to0_label = QLabel("-- ms")
        self._lat_1to0_label.setStyleSheet("font-weight: bold; color: #44aa44;")
        dir2_layout.addWidget(self._lat_1to0_label, 0, 1)
        latency_layout.addLayout(dir2_layout)

        # Summary (Average, P95, P99)
        summary_layout = QGridLayout()
        summary_layout.addWidget(QLabel("Average:"), 0, 0)
        self._lat_avg_label = QLabel("-- ms")
        self._lat_avg_label.setStyleSheet("font-weight: bold; font-size: 14pt; color: #00aaff;")
        summary_layout.addWidget(self._lat_avg_label, 0, 1)

        summary_layout.addWidget(QLabel("P95:"), 1, 0)
        self._lat_p95_label = QLabel("-- ms")
        self._lat_p95_label.setStyleSheet("font-weight: bold; color: #ffaa00;")
        summary_layout.addWidget(self._lat_p95_label, 1, 1)

        summary_layout.addWidget(QLabel("P99:"), 2, 0)
        self._lat_p99_label = QLabel("-- ms")
        self._lat_p99_label.setStyleSheet("font-weight: bold; color: #ff6600;")
        summary_layout.addWidget(self._lat_p99_label, 2, 1)

        latency_layout.addLayout(summary_layout)

        # Samples count
        samples_layout = QGridLayout()
        samples_layout.addWidget(QLabel("Samples:"), 0, 0)
        self._lat_samples_label = QLabel("0")
        samples_layout.addWidget(self._lat_samples_label, 0, 1)
        latency_layout.addLayout(samples_layout)

        layout.addWidget(latency_group)

        # Control buttons
        buttons_layout = QHBoxLayout()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_all)
        buttons_layout.addWidget(refresh_btn)

        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self._reset_counters)
        buttons_layout.addWidget(reset_btn)

        buttons_layout.addStretch()

        # Configurable refresh interval
        buttons_layout.addWidget(QLabel("Refresh:"))
        self._refresh_spin = QSpinBox()
        self._refresh_spin.setRange(100, 5000)
        self._refresh_spin.setValue(1000)
        self._refresh_spin.setSingleStep(100)
        self._refresh_spin.setSuffix(" ms")
        self._refresh_spin.setToolTip("Update interval (100-5000 ms)")
        self._refresh_spin.valueChanged.connect(self._on_refresh_changed)
        buttons_layout.addWidget(self._refresh_spin)

        layout.addLayout(buttons_layout)

        layout.addStretch()

    def _start_live_updates(self):
        """Start periodic live updates."""
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._refresh_all)
        self._update_timer.start(1000)

    def _on_refresh_changed(self, value: int):
        """Handle refresh interval change from spinbox."""
        if self._update_timer:
            self._update_timer.setInterval(value)

    def _update_latency_display(self):
        """Update latency display labels from gateway samples via service."""
        if not self._service:
            self._lat_0to1_label.setText("-- ms")
            self._lat_1to0_label.setText("-- ms")
            self._lat_avg_label.setText("-- ms")
            self._lat_p95_label.setText("-- ms")
            self._lat_p99_label.setText("-- ms")
            self._lat_samples_label.setText("0")
            return

        samples_0to1 = self._service.get_latency_samples("0to1")
        samples_1to0 = self._service.get_latency_samples("1to0")

        if samples_0to1:
            avg_0to1 = sum(samples_0to1) / len(samples_0to1)
            self._lat_0to1_label.setText(f"{avg_0to1 / 1000:.2f} ms")
        else:
            self._lat_0to1_label.setText("-- ms")

        if samples_1to0:
            avg_1to0 = sum(samples_1to0) / len(samples_1to0)
            self._lat_1to0_label.setText(f"{avg_1to0 / 1000:.2f} ms")
        else:
            self._lat_1to0_label.setText("-- ms")

        all_samples = samples_0to1 + samples_1to0
        if all_samples:
            avg_all = sum(all_samples) / len(all_samples)
            self._lat_avg_label.setText(f"{avg_all / 1000:.2f} ms")
            self._lat_samples_label.setText(str(len(all_samples)))

            # Calculate P95 and P99 percentiles
            p95, p99 = self._calculate_percentiles(all_samples, [95, 99])
            self._lat_p95_label.setText(f"{p95 / 1000:.2f} ms")
            self._lat_p99_label.setText(f"{p99 / 1000:.2f} ms")
        else:
            self._lat_avg_label.setText("-- ms")
            self._lat_p95_label.setText("-- ms")
            self._lat_p99_label.setText("-- ms")
            self._lat_samples_label.setText("0")

    def _calculate_percentiles(self, samples: list[float], percentiles: list[int]) -> list[float]:
        """Calculate percentiles from sample data.

        Args:
            samples: List of sample values (in microseconds)
            percentiles: List of percentile values to calculate (e.g., [95, 99])

        Returns:
            List of percentile values in same order as input percentiles
        """
        if not samples:
            return [0.0] * len(percentiles)

        sorted_samples = sorted(samples)
        n = len(sorted_samples)
        results = []

        for p in percentiles:
            # Use nearest-rank method for percentile calculation
            idx = int((p / 100) * n)
            idx = min(idx, n - 1)  # Clamp to valid index
            results.append(sorted_samples[idx])

        return results

    def _get_interface_stats(self, iface: str) -> dict:
        """Read interface statistics from /sys/class/net/."""
        base = f"/sys/class/net/{iface}/statistics/"
        stats = {"rx_packets": 0, "tx_packets": 0, "rx_errors": 0, "tx_errors": 0}
        for key in stats:
            try:
                with open(base + key) as f:
                    stats[key] = int(f.read())
            except (FileNotFoundError, ValueError, OSError):
                pass
        return stats

    def _refresh_all(self):
        """Refresh all statistics."""
        # Update mode
        mode = "Virtual CAN" if self._iface0.startswith("vcan") else "Hardware CAN"
        self._mode_label.setText(mode)

        # Update uptime
        uptime = int(time.time() - self._start_time)
        hours, remainder = divmod(uptime, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            self._uptime_label.setText(f"{hours}h {minutes}m {seconds}s")
        elif minutes > 0:
            self._uptime_label.setText(f"{minutes}m {seconds}s")
        else:
            self._uptime_label.setText(f"{seconds}s")

        # Read interface stats
        stats0 = self._get_interface_stats(self._iface0)
        stats1 = self._get_interface_stats(self._iface1)

        # Update interface statistics table
        for row, (iface, stats) in enumerate([(self._iface0, stats0), (self._iface1, stats1)]):
            prev = self._prev_stats.get(iface, stats)

            rx_rate = stats["rx_packets"] - prev["rx_packets"]
            tx_rate = stats["tx_packets"] - prev["tx_packets"]

            item_rx = self._iface_table.item(row, 1)
            item_tx = self._iface_table.item(row, 2)
            item_rx_rate = self._iface_table.item(row, 3)
            item_tx_rate = self._iface_table.item(row, 4)
            assert item_rx and item_tx and item_rx_rate and item_tx_rate

            item_rx.setText(f"{stats['rx_packets']:,}")
            item_tx.setText(f"{stats['tx_packets']:,}")
            item_rx_rate.setText(f"{rx_rate}")
            item_tx_rate.setText(f"{tx_rate}")

            errors = stats["rx_errors"] + stats["tx_errors"]
            error_item = self._iface_table.item(row, 5)
            assert error_item is not None
            error_item.setText(str(errors))
            if errors > 0:
                error_item.setBackground(Qt.GlobalColor.red)

            self._prev_stats[iface] = stats

        # Update rate labels
        prev0 = self._prev_stats.get(f"{self._iface0}_rate", stats0)
        prev1 = self._prev_stats.get(f"{self._iface1}_rate", stats1)

        rx0_rate = stats0["rx_packets"] - prev0.get("rx_packets", stats0["rx_packets"])
        rx1_rate = stats1["rx_packets"] - prev1.get("rx_packets", stats1["rx_packets"])

        self._rate_0_label.setText(f"{rx0_rate} msg/s")
        self._rate_1_label.setText(f"{rx1_rate} msg/s")
        self._total_rate_label.setText(f"{rx0_rate + rx1_rate} msg/s")

        self._prev_stats[f"{self._iface0}_rate"] = stats0
        self._prev_stats[f"{self._iface1}_rate"] = stats1

        # Update forwarding statistics and latency
        self._update_forwarding_stats()
        self._update_latency_display()

    def _update_forwarding_stats(self):
        """Update forwarding statistics from GatewayService."""
        if not self._service:
            self._fwd_0to1_label.setText("--")
            self._fwd_1to0_label.setText("--")
            self._fwd_total_label.setText("0")
            return

        status = self._service.get_status()
        total_fwd = 0

        # Direction 0 -> 1
        if status.running and status.config.enable_0to1:
            stats = status.stats_0to1
            rx = stats["received"]
            fwd = stats["forwarded"]
            self._fwd_0to1_label.setText(f"RX:{rx:,} → FWD:{fwd:,}")
            total_fwd += fwd
        else:
            self._fwd_0to1_label.setText("--")

        # Direction 1 -> 0
        if status.running and status.config.enable_1to0:
            stats = status.stats_1to0
            rx = stats["received"]
            fwd = stats["forwarded"]
            self._fwd_1to0_label.setText(f"RX:{rx:,} → FWD:{fwd:,}")
            total_fwd += fwd
        else:
            self._fwd_1to0_label.setText("--")

        self._fwd_total_label.setText(f"{total_fwd:,}")

    def _reset_counters(self):
        """Reset all counters."""
        self._start_time = time.time()
        self._prev_stats.clear()
        # Clear gateway latency samples via service
        if self._service:
            self._service.clear_latency_samples()
        self._update_latency_display()

    def stop(self):
        """Stop live updates."""
        if self._update_timer:
            self._update_timer.stop()

    def refresh(self):
        """Manually refresh all statistics (F5 shortcut)."""
        self._refresh_all()

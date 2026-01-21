"""Traffic Control widget - CAN gateway control using GatewayService.

Provides UI controls for:
- Interface management (up/down)
- Gateway start/stop with direction control
- Traffic control settings (delay, packet loss)
- Forwarding statistics display
"""

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from wp4.core.gateway_manager import GatewayConfig
from wp4.gui.adapters.qt_events import QtEventAdapter
from wp4.gui.config import get_default_config
from wp4.lib import is_virtual_can
from wp4.services.gateway_service import GatewayService


class _InterfaceStatusSignals(QObject):
    """Signals for thread-safe interface status updates."""

    status_ready = Signal(str, object)  # iface, state


class TrafficControlWidget(QWidget):
    """Widget for CAN gateway control.

    Uses GatewayService for all gateway operations, eliminating direct
    access to business logic.
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
        self._is_virtual = is_virtual_can(iface0)
        self._bitrate = 500000

        # Create service if not provided (backwards compatibility)
        if service is None:
            config = GatewayConfig(
                iface0=iface0,
                iface1=iface1,
                delay_ms=0,
                loss_pct=0.0,
                enable_0to1=True,
                enable_1to0=True,
            )
            self._service = GatewayService(config)
            self._event_adapter = QtEventAdapter(self._service.get_event_bus(), parent=self)
        else:
            self._service = service
            self._event_adapter = event_adapter or QtEventAdapter(
                service.get_event_bus(), parent=self
            )

        # Interface status signals
        self._status_signals = _InterfaceStatusSignals()
        self._status_signals.status_ready.connect(self._on_status_ready)

        # Connect to gateway events
        if self._event_adapter:
            self._event_adapter.gateway_started.connect(self._on_gateway_started)
            self._event_adapter.gateway_stopped.connect(self._on_gateway_stopped)
            self._event_adapter.interface_state_changed.connect(self._on_interface_state_changed)

        self._setup_ui()

        # Auto-refresh stats
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._refresh_stats)
        self._stats_timer.start(500)

        # Initial status
        QTimer.singleShot(100, self._refresh_interface_status)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Interface controls
        if_group = QGroupBox("Interfaces")
        if_layout = QGridLayout(if_group)

        # Bitrate (only for real CAN)
        if not self._is_virtual:
            if_layout.addWidget(QLabel("Bitrate:"), 0, 0)
            self._bitrate_spin = QSpinBox()
            self._bitrate_spin.setRange(10000, 1000000)
            self._bitrate_spin.setValue(500000)
            self._bitrate_spin.setSingleStep(50000)
            self._bitrate_spin.setSuffix(" bps")
            self._bitrate_spin.valueChanged.connect(self._on_bitrate_changed)
            if_layout.addWidget(self._bitrate_spin, 0, 1, 1, 2)

        # Interface 0
        row_start = 1 if not self._is_virtual else 0
        self._if0_status = QLabel(f"{self._iface0}: --")
        self._if0_status.setMinimumWidth(150)
        if_layout.addWidget(self._if0_status, row_start, 0)
        if0_up_btn = QPushButton("Up")
        if0_up_btn.clicked.connect(lambda: self._interface_up(self._iface0))
        if_layout.addWidget(if0_up_btn, row_start, 1)
        if0_down_btn = QPushButton("Down")
        if0_down_btn.clicked.connect(lambda: self._interface_down(self._iface0))
        if_layout.addWidget(if0_down_btn, row_start, 2)

        # Interface 1
        self._if1_status = QLabel(f"{self._iface1}: --")
        self._if1_status.setMinimumWidth(150)
        if_layout.addWidget(self._if1_status, row_start + 1, 0)
        if1_up_btn = QPushButton("Up")
        if1_up_btn.clicked.connect(lambda: self._interface_up(self._iface1))
        if_layout.addWidget(if1_up_btn, row_start + 1, 1)
        if1_down_btn = QPushButton("Down")
        if1_down_btn.clicked.connect(lambda: self._interface_down(self._iface1))
        if_layout.addWidget(if1_down_btn, row_start + 1, 2)

        # Both up/down
        both_row = QHBoxLayout()
        both_up_btn = QPushButton("Both Up")
        both_up_btn.clicked.connect(self._both_up)
        both_row.addWidget(both_up_btn)
        both_down_btn = QPushButton("Both Down")
        both_down_btn.clicked.connect(self._both_down)
        both_row.addWidget(both_down_btn)
        if_layout.addLayout(both_row, row_start + 2, 0, 1, 3)

        layout.addWidget(if_group)

        # Gateway controls
        fwd_group = QGroupBox("Gateway")
        fwd_layout = QVBoxLayout(fwd_group)

        # Direction 0 -> 1
        row1 = QHBoxLayout()
        self._enable_0to1 = QCheckBox(f"{self._iface0} → {self._iface1}")
        self._enable_0to1.stateChanged.connect(self._toggle_0to1)
        row1.addWidget(self._enable_0to1)
        self._status_0to1 = QLabel("stopped")
        self._status_0to1.setStyleSheet("color: #888;")
        row1.addWidget(self._status_0to1)
        row1.addStretch()
        fwd_layout.addLayout(row1)

        # Direction 1 -> 0
        row2 = QHBoxLayout()
        self._enable_1to0 = QCheckBox(f"{self._iface1} → {self._iface0}")
        self._enable_1to0.stateChanged.connect(self._toggle_1to0)
        row2.addWidget(self._enable_1to0)
        self._status_1to0 = QLabel("stopped")
        self._status_1to0.setStyleSheet("color: #888;")
        row2.addWidget(self._status_1to0)
        row2.addStretch()
        fwd_layout.addLayout(row2)

        # Quick actions
        quick_layout = QHBoxLayout()
        enable_both_btn = QPushButton("Enable Both")
        enable_both_btn.clicked.connect(self._enable_both)
        quick_layout.addWidget(enable_both_btn)

        disable_both_btn = QPushButton("Disable Both")
        disable_both_btn.clicked.connect(self._disable_both)
        disable_both_btn.setStyleSheet("background-color: #cc4444;")
        quick_layout.addWidget(disable_both_btn)
        fwd_layout.addLayout(quick_layout)

        layout.addWidget(fwd_group)

        # Traffic Control (delay/loss settings)
        tc_group = QGroupBox("Traffic Control")
        tc_layout = QGridLayout(tc_group)

        tc_layout.addWidget(QLabel("Delay (ms):"), 0, 0)
        self._delay_spin = QSpinBox()
        self._delay_spin.setRange(0, 10000)
        self._delay_spin.setValue(0)
        self._delay_spin.setSuffix(" ms")
        self._delay_spin.valueChanged.connect(self._update_settings)
        tc_layout.addWidget(self._delay_spin, 0, 1)

        tc_layout.addWidget(QLabel("Packet Loss (%):"), 1, 0)
        self._loss_spin = QDoubleSpinBox()
        self._loss_spin.setRange(0.0, 100.0)
        self._loss_spin.setValue(0.0)
        self._loss_spin.setSingleStep(1.0)
        self._loss_spin.setDecimals(1)
        self._loss_spin.setSuffix(" %")
        self._loss_spin.valueChanged.connect(self._update_settings)
        tc_layout.addWidget(self._loss_spin, 1, 1)

        tc_layout.addWidget(QLabel("Jitter (±ms):"), 2, 0)
        self._jitter_spin = QDoubleSpinBox()
        self._jitter_spin.setRange(0.0, 1000.0)
        self._jitter_spin.setValue(0.0)
        self._jitter_spin.setSingleStep(1.0)
        self._jitter_spin.setDecimals(1)
        self._jitter_spin.setSuffix(" ms")
        self._jitter_spin.setToolTip(
            "Symmetric jitter: delay ± jitter\n"
            "Example: delay=50ms, jitter=10ms → 40-60ms\n"
            "Note: Delay is auto-adjusted to match jitter if needed."
        )
        self._jitter_spin.valueChanged.connect(self._update_settings)
        tc_layout.addWidget(self._jitter_spin, 2, 1)

        layout.addWidget(tc_group)

        # Logging controls
        log_group = QGroupBox("Logging")
        log_layout = QGridLayout(log_group)

        self._log_btn = QPushButton("Start Logging")
        self._log_btn.setCheckable(True)
        self._log_btn.clicked.connect(self._toggle_logging)
        log_layout.addWidget(self._log_btn, 0, 0, 1, 3)
        self._logging_active = False

        log_layout.addWidget(QLabel("Log Path:"), 1, 0)
        self._log_path_edit = QLineEdit()
        # Use project logs directory from central config
        default_log_path = get_default_config().logging.default_path
        self._log_path_edit.setText(str(default_log_path))
        self._log_path_edit.setReadOnly(True)
        log_layout.addWidget(self._log_path_edit, 1, 1)

        self._log_browse_btn = QPushButton("Browse...")
        self._log_browse_btn.clicked.connect(self._browse_log_path)
        log_layout.addWidget(self._log_browse_btn, 1, 2)

        log_layout.addWidget(QLabel("Filename:"), 2, 0)
        self._log_name_edit = QLineEdit()
        self._log_name_edit.setPlaceholderText("(auto: gateway_YYYYMMDD_HHMMSS.blf)")
        self._log_name_edit.setToolTip(
            "Custom filename for the BLF log file.\n"
            "Leave empty for automatic timestamp-based naming.\n"
            "Extension .blf will be added automatically."
        )
        log_layout.addWidget(self._log_name_edit, 2, 1, 1, 2)

        # Show active log files
        self._log_files_label = QLabel("Active: --")
        self._log_files_label.setStyleSheet("font-family: monospace; font-size: 10px;")
        log_layout.addWidget(self._log_files_label, 3, 0, 1, 3)

        # Export buttons
        export_row = QHBoxLayout()

        self._export_btn = QPushButton("Export Active")
        self._export_btn.setToolTip(
            "Export active BLF to all formats:\n"
            "- ASC (CANalyzer/CANoe replay)\n"
            "- Human-readable log\n"
            "- Detailed analysis with per-frame data"
        )
        self._export_btn.clicked.connect(self._export_active)
        self._export_btn.setEnabled(False)
        export_row.addWidget(self._export_btn)

        self._export_file_btn = QPushButton("Export File...")
        self._export_file_btn.setToolTip(
            "Select a BLF file to export:\n"
            "- ASC (CANalyzer/CANoe replay)\n"
            "- Human-readable log\n"
            "- Detailed analysis with per-frame data"
        )
        self._export_file_btn.clicked.connect(self._export_file)
        export_row.addWidget(self._export_file_btn)

        log_layout.addLayout(export_row, 4, 0, 1, 3)

        layout.addWidget(log_group)

        # Statistics
        stats_group = QGroupBox("Forwarding Statistics")
        stats_layout = QGridLayout(stats_group)

        stats_layout.addWidget(QLabel(f"{self._iface0} → {self._iface1}:"), 0, 0)
        self._stats_0to1 = QLabel("--")
        self._stats_0to1.setStyleSheet("font-family: monospace;")
        stats_layout.addWidget(self._stats_0to1, 0, 1)

        stats_layout.addWidget(QLabel(f"{self._iface1} → {self._iface0}:"), 1, 0)
        self._stats_1to0 = QLabel("--")
        self._stats_1to0.setStyleSheet("font-family: monospace;")
        stats_layout.addWidget(self._stats_1to0, 1, 1)

        layout.addWidget(stats_group)

        # Quick start/stop
        quick_group = QGroupBox("Quick Actions")
        quick_group_layout = QHBoxLayout(quick_group)

        start_all_btn = QPushButton("Start All")
        start_all_btn.setStyleSheet("background-color: #44aa44;")
        start_all_btn.clicked.connect(self._start_all)
        quick_group_layout.addWidget(start_all_btn)

        stop_all_btn = QPushButton("Stop All")
        stop_all_btn.setStyleSheet("background-color: #cc4444;")
        stop_all_btn.clicked.connect(self._stop_all)
        quick_group_layout.addWidget(stop_all_btn)

        layout.addWidget(quick_group)

        layout.addStretch()

    # Interface controls
    def _on_bitrate_changed(self, value: int):
        """Handle bitrate change."""
        self._bitrate = value
        self._service.set_bitrate(value)

    def _interface_up(self, iface: str):
        """Bring up a single interface."""
        try:
            # Set bitrate first
            self._service.set_bitrate(self._bitrate)
            # Bring up single interface
            self._service.bring_up_interface(iface)
            self._refresh_interface_status()
        except PermissionError:
            QMessageBox.warning(
                self,
                "Permission Denied",
                f"No permission for interface {iface}.\n"
                "Please run with sudo or add user to 'can' group.",
            )
        except Exception as e:
            QMessageBox.warning(self, "Interface Error", str(e))

    def _interface_down(self, iface: str):
        """Bring down a single interface."""
        try:
            self._service.bring_down_interface(iface)
            self._refresh_interface_status()
        except PermissionError:
            QMessageBox.warning(
                self,
                "Permission Denied",
                f"No permission for interface {iface}.\nPlease run with sudo.",
            )
        except Exception as e:
            QMessageBox.warning(self, "Interface Error", str(e))

    def _both_up(self):
        """Bring up both interfaces."""
        try:
            self._service.set_bitrate(self._bitrate)
            self._service.bring_up_interfaces()
            self._refresh_interface_status()
        except PermissionError:
            QMessageBox.warning(
                self,
                "Permission Denied",
                "No permission for interfaces.\nPlease run with sudo or add user to 'can' group.",
            )
        except Exception as e:
            QMessageBox.warning(self, "Interface Error", str(e))

    def _both_down(self):
        """Bring down both interfaces."""
        try:
            self._service.bring_down_interfaces()
            self._refresh_interface_status()
        except PermissionError:
            QMessageBox.warning(
                self,
                "Permission Denied",
                "No permission for interfaces.\nPlease run with sudo.",
            )
        except Exception as e:
            QMessageBox.warning(self, "Interface Error", str(e))

    def _refresh_interface_status(self):
        """Refresh interface status display."""
        states = self._service.get_interface_states()

        for iface, state in states.items():
            self._status_signals.status_ready.emit(iface, state)

    def _on_status_ready(self, iface: str, state):
        """Handle interface status update (runs in main thread)."""
        label = self._if0_status if iface == self._iface0 else self._if1_status
        if state:
            br = f" @ {state.bitrate}" if state.bitrate else ""
            color = "#44aa44" if state.state == "UP" else "#888"
            label.setText(f"{iface}: {state.state}{br}")
            label.setStyleSheet(f"color: {color}; font-weight: bold;")
        else:
            label.setText(f"{iface}: not found")
            label.setStyleSheet("color: #cc4444;")

    def _on_interface_state_changed(self, iface: str, state):
        """Handle interface state change event from EventBus."""
        self._status_signals.status_ready.emit(iface, state)

    # Gateway controls
    def _toggle_0to1(self, state: int):
        """Toggle 0→1 direction."""
        if state:
            self._enable_0to1_direction()
        else:
            self._disable_0to1_direction()

    def _toggle_1to0(self, state: int):
        """Toggle 1→0 direction."""
        if state:
            self._enable_1to0_direction()
        else:
            self._disable_1to0_direction()

    def _enable_0to1_direction(self):
        """Enable 0→1 direction and start gateway if needed."""
        # Start gateway if not running
        if not self._service.is_running():
            self._service.start()

        self._service.enable_direction("0to1")
        self._update_direction_status()

    def _disable_0to1_direction(self):
        """Disable 0→1 direction and stop gateway if both disabled."""
        self._service.disable_direction("0to1")

        # Stop gateway if both directions disabled
        config = self._service.get_config()
        if not config.enable_0to1 and not config.enable_1to0:
            self._service.stop()

    def _enable_1to0_direction(self):
        """Enable 1→0 direction and start gateway if needed."""
        # Start gateway if not running
        if not self._service.is_running():
            self._service.start()

        self._service.enable_direction("1to0")
        self._update_direction_status()

    def _disable_1to0_direction(self):
        """Disable 1→0 direction and stop gateway if both disabled."""
        self._service.disable_direction("1to0")

        # Stop gateway if both directions disabled
        config = self._service.get_config()
        if not config.enable_0to1 and not config.enable_1to0:
            self._service.stop()

    def _enable_both(self):
        """Enable both directions."""
        self._enable_0to1.setChecked(True)
        self._enable_1to0.setChecked(True)

    def _disable_both(self):
        """Disable both directions."""
        self._enable_0to1.setChecked(False)
        self._enable_1to0.setChecked(False)

    def _update_settings(self):
        """Update gateway settings (delay, packet loss, and jitter)."""
        delay = self._delay_spin.value()
        loss = self._loss_spin.value()
        jitter = self._jitter_spin.value()

        # Ensure delay >= jitter for symmetric jitter (delay ± jitter)
        if jitter > delay:
            delay = int(jitter)
            self._delay_spin.blockSignals(True)
            self._delay_spin.setValue(delay)
            self._delay_spin.blockSignals(False)

        # Validate extreme values and warn user
        self._check_extreme_values(delay, loss, jitter)

        self._service.update_settings(delay_ms=delay, loss_pct=loss, jitter_ms=jitter)

        # Update status labels
        status_text = f"running (delay={delay}ms±{jitter}ms, loss={loss}%)"
        if self._enable_0to1.isChecked():
            self._status_0to1.setText(status_text)
        if self._enable_1to0.isChecked():
            self._status_1to0.setText(status_text)

    def _check_extreme_values(self, delay: int, loss: float, jitter: float):
        """Check for extreme values and warn user once per threshold crossing."""
        warnings = []

        # High packet loss warning (> 50%)
        if loss > 50 and not getattr(self, "_warned_high_loss", False):
            warnings.append(
                f"Packet loss {loss}% is very high!\nThis will cause significant data loss."
            )
            self._warned_high_loss = True
        elif loss <= 50:
            self._warned_high_loss = False

        # Jitter > delay warning
        if jitter > delay > 0 and not getattr(self, "_warned_jitter_delay", False):
            warnings.append(
                f"Jitter ({jitter}ms) is greater than delay ({delay}ms)!\n"
                "This may cause negative effective delays."
            )
            self._warned_jitter_delay = True
        elif jitter <= delay or delay == 0:
            self._warned_jitter_delay = False

        # Very high delay warning (> 5000ms)
        if delay > 5000 and not getattr(self, "_warned_high_delay", False):
            warnings.append(
                f"Delay {delay}ms is very high!\nThis may cause timeouts and buffer overflows."
            )
            self._warned_high_delay = True
        elif delay <= 5000:
            self._warned_high_delay = False

        # Show combined warning if any
        if warnings:
            QMessageBox.warning(
                self,
                "Extreme Values",
                "\n\n".join(warnings),
            )

    def _update_direction_status(self):
        """Update direction status labels based on current state."""
        if not self._service.is_running():
            self._status_0to1.setText("stopped")
            self._status_0to1.setStyleSheet("color: #888;")
            self._status_1to0.setText("stopped")
            self._status_1to0.setStyleSheet("color: #888;")
            return

        config = self._service.get_config()
        delay = config.delay_ms
        jitter = config.jitter_ms
        loss = config.loss_pct
        status_text = f"running (delay={delay}ms±{jitter}ms, loss={loss}%)"

        if self._enable_0to1.isChecked():
            self._status_0to1.setText(status_text)
            self._status_0to1.setStyleSheet("color: #44aa44; font-weight: bold;")
        else:
            self._status_0to1.setText("stopped")
            self._status_0to1.setStyleSheet("color: #888;")

        if self._enable_1to0.isChecked():
            self._status_1to0.setText(status_text)
            self._status_1to0.setStyleSheet("color: #44aa44; font-weight: bold;")
        else:
            self._status_1to0.setText("stopped")
            self._status_1to0.setStyleSheet("color: #888;")

    def _on_gateway_started(self, data):
        """Handle GATEWAY_STARTED event."""
        self._update_direction_status()
        # Update log files label if logging is enabled
        if self._logging_active:
            self._update_log_files_label()

    def _on_gateway_stopped(self):
        """Handle GATEWAY_STOPPED event."""
        self._status_0to1.setText("stopped")
        self._status_0to1.setStyleSheet("color: #888;")
        self._status_1to0.setText("stopped")
        self._status_1to0.setStyleSheet("color: #888;")

    def _refresh_stats(self):
        """Update gateway statistics display."""
        status = self._service.get_status()

        if self._enable_0to1.isChecked() and status.running:
            stats = status.stats_0to1
            rx = stats["received"]
            fwd = stats["forwarded"]
            drop = stats["dropped"]
            q = stats["queue_size"]
            self._stats_0to1.setText(f"RX:{rx:,} → FWD:{fwd:,} (drop:{drop}, q:{q})")
        else:
            self._stats_0to1.setText("--")

        if self._enable_1to0.isChecked() and status.running:
            stats = status.stats_1to0
            rx = stats["received"]
            fwd = stats["forwarded"]
            drop = stats["dropped"]
            q = stats["queue_size"]
            self._stats_1to0.setText(f"RX:{rx:,} → FWD:{fwd:,} (drop:{drop}, q:{q})")
        else:
            self._stats_1to0.setText("--")

    # Logging controls
    def _toggle_logging(self, checked: bool):
        """Toggle logging on/off."""
        if checked:
            log_path = self._log_path_edit.text()
            log_name = self._log_name_edit.text().strip() or None
            self._service.set_log_path(log_path, custom_name=log_name)
            self._update_log_files_label()
            self._log_btn.setText("Stop Logging")
            self._logging_active = True
        else:
            self._service.set_log_path(None)
            self._log_files_label.setText("Active: --")
            self._log_btn.setText("Start Logging")
            self._logging_active = False

    def _browse_log_path(self):
        """Open file dialog to select log directory."""
        current_path = self._log_path_edit.text()
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Log Directory",
            current_path,
            QFileDialog.Option.ShowDirsOnly,
        )
        if path:
            self._log_path_edit.setText(path)
            # Update service if logging is enabled
            if self._logging_active:
                self._service.set_log_path(path)
                self._update_log_files_label()

    def _update_log_files_label(self):
        """Update the log files label with current paths."""
        log_paths = self._service.get_log_paths()
        blf_path = log_paths.get("0to1")  # Both directions use same BLF file

        if blf_path and blf_path.exists():
            self._log_files_label.setText(f"Active: {blf_path.name}")
            # Enable export button when BLF file exists
            self._export_btn.setEnabled(True)
        else:
            self._log_files_label.setText("Active: --")
            self._export_btn.setEnabled(False)

    def _export_active(self):
        """Export active BLF to all formats at once."""
        log_paths = self._service.get_log_paths()
        blf_path = log_paths.get("0to1")

        if blf_path and blf_path.exists():
            self._do_export(blf_path)
        else:
            QMessageBox.warning(self, "No Log File", "No active BLF log file to export.")

    def _export_file(self):
        """Open file dialog to select BLF file for export."""
        # Start in log directory if available
        start_dir = self._log_path_edit.text()

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select BLF File to Export",
            start_dir,
            "BLF Files (*.blf);;All Files (*)",
        )
        if path:
            self._do_export(Path(path))

    def _do_export(self, blf_path: Path):
        """Export a BLF file to all formats."""
        try:
            from wp4.core.log_exporter import LogExporter

            # Pass interface names for ASC filenames
            result = LogExporter.export_all(blf_path, self._iface0, self._iface1)

            QMessageBox.information(
                self,
                "Export Complete",
                f"Created files:\n\n"
                f"ASC ({self._iface0}): {result['asc_ch1'].name}\n"
                f"ASC ({self._iface1}): {result['asc_ch2'].name}\n"
                f"Log (readable):  {result['log'].name}\n"
                f"Analysis:        {result['analysis'].name}\n\n"
                f"Location: {blf_path.parent}",
            )
        except Exception as e:
            QMessageBox.warning(self, "Export Error", f"Failed to export:\n{e}")

    # Quick actions
    def _start_all(self):
        """Start interfaces and enable both directions."""
        self._both_up()
        self._enable_both()

    def _stop_all(self):
        """Stop gateway and bring interfaces down."""
        self._disable_both()
        self._both_down()

    # Public API for keyboard shortcuts
    def start_gateway(self):
        """Start the gateway (for keyboard shortcut Ctrl+G)."""
        self._start_all()

    def stop_gateway(self):
        """Stop the gateway (for keyboard shortcut Ctrl+H)."""
        self._stop_all()

    def stop(self):
        """Stop all (cleanup on close)."""
        if self._service.is_running():
            self._service.stop()
        if self._stats_timer:
            self._stats_timer.stop()

    # Backward compatibility
    def remove_all_tc(self):
        """Alias for stop()."""
        self.stop()

    # For StatisticsWidget compatibility
    def get_gateway_service(self) -> GatewayService:
        """Get the gateway service.

        Returns:
            GatewayService instance
        """
        return self._service

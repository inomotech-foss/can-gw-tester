"""Main application window for CAN Gateway GUI."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from wp4.core.gateway_manager import GatewayConfig
from wp4.gui.adapters.qt_events import QtEventAdapter
from wp4.gui.widgets.can_frame_view import CanFrameViewWidget
from wp4.gui.widgets.manipulation_widget import ManipulationWidget
from wp4.gui.widgets.statistics import StatisticsWidget
from wp4.gui.widgets.traffic_control import TrafficControlWidget
from wp4.services.gateway_service import GatewayService


class MainWindow(QMainWindow):
    """Main window for CAN Gateway management."""

    def __init__(self, virtual: bool = False):
        super().__init__()

        # Determine interfaces
        self._iface0 = "vcan0" if virtual else "can0"
        self._iface1 = "vcan1" if virtual else "can1"
        self._virtual = virtual

        # Create gateway configuration
        self._config = GatewayConfig(
            iface0=self._iface0,
            iface1=self._iface1,
            delay_ms=0,
            loss_pct=0.0,
            enable_0to1=True,
            enable_1to0=True,
        )

        # Create gateway service
        self._service = GatewayService(self._config)

        # Create Qt event adapter
        self._event_adapter = QtEventAdapter(self._service.get_event_bus(), parent=self)

        mode = "Virtual" if virtual else "Hardware"
        self.setWindowTitle(f"CAN Gateway ({mode}) - {self._iface0} <-> {self._iface1}")
        self.setMinimumSize(1400, 800)

        self._setup_ui()
        self._setup_status_bar()
        self._setup_shortcuts()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)

        # Left side: Gateway/Traffic control (inject shared service)
        self._tc_widget = TrafficControlWidget(
            self._iface0,
            self._iface1,
            service=self._service,
            event_adapter=self._event_adapter,
        )
        self._tc_widget.setMaximumWidth(400)
        main_layout.addWidget(self._tc_widget)

        # Center: Tabs (CAN Frames, Traffic Generator)
        center_layout = QVBoxLayout()

        # Header
        header = QLabel(f"<h2>CAN Gateway</h2><p>{self._iface0} <-> {self._iface1}</p>")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(header)

        # Tab widget
        tabs = QTabWidget()

        # CAN Frame View tab (first/default)
        self._frame_view_widget = CanFrameViewWidget(self._iface0, self._iface1)
        tabs.addTab(self._frame_view_widget, "CAN Frames")

        # Manipulation Rules tab
        self._manipulation_widget = ManipulationWidget(self._service)
        tabs.addTab(self._manipulation_widget, "Manipulation")

        center_layout.addWidget(tabs)
        main_layout.addLayout(center_layout, stretch=1)

        # Right side: Statistics (permanent panel, inject shared service)
        self._stats_widget = StatisticsWidget(
            self._iface0,
            self._iface1,
            service=self._service,
            event_adapter=self._event_adapter,
        )
        self._stats_widget.setMaximumWidth(350)
        self._stats_widget.setMinimumWidth(300)
        main_layout.addWidget(self._stats_widget)

    def _setup_status_bar(self):
        status_bar = QStatusBar()
        mode = "Virtual CAN (vcan)" if self._virtual else "Hardware CAN"
        status_bar.showMessage(f"Mode: {mode} | Interfaces: {self._iface0}, {self._iface1}")
        self.setStatusBar(status_bar)

    def _setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        # Ctrl+G = Gateway Start
        start_shortcut = QShortcut(QKeySequence("Ctrl+G"), self)
        start_shortcut.activated.connect(self._tc_widget.start_gateway)

        # Ctrl+H = Gateway Halt (Stop)
        stop_shortcut = QShortcut(QKeySequence("Ctrl+H"), self)
        stop_shortcut.activated.connect(self._tc_widget.stop_gateway)

        # F5 = Refresh statistics
        refresh_shortcut = QShortcut(QKeySequence("F5"), self)
        refresh_shortcut.activated.connect(self._stats_widget.refresh)

    def closeEvent(self, event):
        """Cleanup on close with confirmation if gateway is running."""
        if self._service.is_running():
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Gateway Active")
            msg_box.setText("The gateway is still running!")
            msg_box.setInformativeText("Do you really want to quit?")
            msg_box.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
            )
            msg_box.setDefaultButton(QMessageBox.StandardButton.Cancel)
            msg_box.setIcon(QMessageBox.Icon.Warning)

            if msg_box.exec() == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return

        self._tc_widget.stop()
        self._stats_widget.stop()
        self._frame_view_widget.stop()
        super().closeEvent(event)

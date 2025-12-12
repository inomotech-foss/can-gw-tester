"""Interface Control widget - CAN interface management.

Provides UI controls for:
- Interface up/down control
- Bitrate configuration (for real CAN interfaces)
- Interface status display
"""

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QWidget,
)

from wp4.lib import is_virtual_can
from wp4.services.gateway_service import GatewayService


class _InterfaceStatusSignals(QObject):
    """Signals for thread-safe interface status updates."""

    status_ready = Signal(str, object)  # iface, state


class InterfaceControlWidget(QWidget):
    """Widget for CAN interface control.

    Provides controls for bringing interfaces up/down and setting bitrate.
    """

    def __init__(
        self,
        iface0: str,
        iface1: str,
        service: GatewayService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._iface0 = iface0
        self._iface1 = iface1
        self._service = service
        self._is_virtual = is_virtual_can(iface0)
        self._bitrate = 500000

        # Interface status signals for thread-safe updates
        self._status_signals = _InterfaceStatusSignals()
        self._status_signals.status_ready.connect(self._on_status_ready)

        self._setup_ui()

    def _setup_ui(self):
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Bitrate (only for real CAN)
        row = 0
        if not self._is_virtual:
            layout.addWidget(QLabel("Bitrate:"), row, 0)
            self._bitrate_spin = QSpinBox()
            self._bitrate_spin.setRange(10000, 1000000)
            self._bitrate_spin.setValue(500000)
            self._bitrate_spin.setSingleStep(50000)
            self._bitrate_spin.setSuffix(" bps")
            self._bitrate_spin.valueChanged.connect(self._on_bitrate_changed)
            layout.addWidget(self._bitrate_spin, row, 1, 1, 2)
            row += 1

        # Interface 0
        self._if0_status = QLabel(f"{self._iface0}: --")
        self._if0_status.setMinimumWidth(150)
        layout.addWidget(self._if0_status, row, 0)

        if0_up_btn = QPushButton("Up")
        if0_up_btn.clicked.connect(lambda: self._interface_up(self._iface0))
        layout.addWidget(if0_up_btn, row, 1)

        if0_down_btn = QPushButton("Down")
        if0_down_btn.clicked.connect(lambda: self._interface_down(self._iface0))
        layout.addWidget(if0_down_btn, row, 2)
        row += 1

        # Interface 1
        self._if1_status = QLabel(f"{self._iface1}: --")
        self._if1_status.setMinimumWidth(150)
        layout.addWidget(self._if1_status, row, 0)

        if1_up_btn = QPushButton("Up")
        if1_up_btn.clicked.connect(lambda: self._interface_up(self._iface1))
        layout.addWidget(if1_up_btn, row, 1)

        if1_down_btn = QPushButton("Down")
        if1_down_btn.clicked.connect(lambda: self._interface_down(self._iface1))
        layout.addWidget(if1_down_btn, row, 2)
        row += 1

        # Both up/down
        both_row = QHBoxLayout()
        both_up_btn = QPushButton("Both Up")
        both_up_btn.clicked.connect(self.bring_up_both)
        both_row.addWidget(both_up_btn)

        both_down_btn = QPushButton("Both Down")
        both_down_btn.clicked.connect(self.bring_down_both)
        both_row.addWidget(both_down_btn)

        layout.addLayout(both_row, row, 0, 1, 3)

    def _on_bitrate_changed(self, value: int):
        """Handle bitrate spinbox change."""
        self._bitrate = value
        self._service.set_bitrate(value)

    def _interface_up(self, iface: str):
        """Bring up a single interface."""
        try:
            self._service.set_bitrate(self._bitrate)
            self._service.bring_up_interfaces()
            self.refresh_status()
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
            self._service.bring_down_interfaces()
            self.refresh_status()
        except PermissionError:
            QMessageBox.warning(
                self,
                "Permission Denied",
                f"No permission for interface {iface}.\nPlease run with sudo.",
            )
        except Exception as e:
            QMessageBox.warning(self, "Interface Error", str(e))

    def bring_up_both(self):
        """Bring up both interfaces."""
        try:
            self._service.set_bitrate(self._bitrate)
            self._service.bring_up_interfaces()
            self.refresh_status()
        except PermissionError:
            QMessageBox.warning(
                self,
                "Permission Denied",
                "No permission for interfaces.\nPlease run with sudo or add user to 'can' group.",
            )
        except Exception as e:
            QMessageBox.warning(self, "Interface Error", str(e))

    def bring_down_both(self):
        """Bring down both interfaces."""
        try:
            self._service.bring_down_interfaces()
            self.refresh_status()
        except PermissionError:
            QMessageBox.warning(
                self,
                "Permission Denied",
                "No permission for interfaces.\nPlease run with sudo.",
            )
        except Exception as e:
            QMessageBox.warning(self, "Interface Error", str(e))

    def refresh_status(self):
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

    def on_interface_state_changed(self, iface: str, state):
        """Handle interface state change event from EventBus."""
        self._status_signals.status_ready.emit(iface, state)

    def get_if0_status_label(self) -> QLabel:
        """Get interface 0 status label (for testing)."""
        return self._if0_status

    def get_if1_status_label(self) -> QLabel:
        """Get interface 1 status label (for testing)."""
        return self._if1_status


def create_interface_group(
    iface0: str,
    iface1: str,
    service: GatewayService,
) -> tuple[QGroupBox, InterfaceControlWidget]:
    """Create an interface control group box.

    Args:
        iface0: First interface name
        iface1: Second interface name
        service: Gateway service instance

    Returns:
        Tuple of (QGroupBox, InterfaceControlWidget)
    """
    group = QGroupBox("Interfaces")
    widget = InterfaceControlWidget(iface0, iface1, service)
    layout = QHBoxLayout(group)
    layout.addWidget(widget)
    return group, widget

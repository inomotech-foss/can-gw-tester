"""Gateway Control widget - direction enable/disable.

Provides UI controls for:
- Enable/disable forwarding directions (0to1, 1to0)
- Start/stop gateway
- Direction status display
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wp4.services.gateway_service import GatewayService


class GatewayControlWidget(QWidget):
    """Widget for gateway direction control.

    Provides controls for enabling/disabling forwarding directions
    and displays current status.
    """

    # Signals
    direction_changed = Signal(str, bool)  # direction, enabled

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

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Direction 0 -> 1
        row1 = QHBoxLayout()
        self._enable_0to1 = QCheckBox(f"{self._iface0} \u2192 {self._iface1}")
        self._enable_0to1.stateChanged.connect(self._toggle_0to1)
        row1.addWidget(self._enable_0to1)
        self._status_0to1 = QLabel("stopped")
        self._status_0to1.setStyleSheet("color: #888;")
        row1.addWidget(self._status_0to1)
        row1.addStretch()
        layout.addLayout(row1)

        # Direction 1 -> 0
        row2 = QHBoxLayout()
        self._enable_1to0 = QCheckBox(f"{self._iface1} \u2192 {self._iface0}")
        self._enable_1to0.stateChanged.connect(self._toggle_1to0)
        row2.addWidget(self._enable_1to0)
        self._status_1to0 = QLabel("stopped")
        self._status_1to0.setStyleSheet("color: #888;")
        row2.addWidget(self._status_1to0)
        row2.addStretch()
        layout.addLayout(row2)

        # Quick actions
        quick_layout = QHBoxLayout()
        enable_both_btn = QPushButton("Enable Both")
        enable_both_btn.clicked.connect(self.enable_both)
        quick_layout.addWidget(enable_both_btn)

        disable_both_btn = QPushButton("Disable Both")
        disable_both_btn.clicked.connect(self.disable_both)
        disable_both_btn.setStyleSheet("background-color: #cc4444;")
        quick_layout.addWidget(disable_both_btn)
        layout.addLayout(quick_layout)

    def _toggle_0to1(self, state: int):
        """Toggle 0to1 direction."""
        if state:
            self._enable_direction("0to1")
        else:
            self._disable_direction("0to1")
        self.direction_changed.emit("0to1", bool(state))

    def _toggle_1to0(self, state: int):
        """Toggle 1to0 direction."""
        if state:
            self._enable_direction("1to0")
        else:
            self._disable_direction("1to0")
        self.direction_changed.emit("1to0", bool(state))

    def _enable_direction(self, direction: str):
        """Enable a direction and start gateway if needed."""
        if not self._service.is_running():
            self._service.start()
        self._service.enable_direction(direction)
        self._update_status()

    def _disable_direction(self, direction: str):
        """Disable a direction and stop gateway if both disabled."""
        self._service.disable_direction(direction)
        config = self._service.get_config()
        if not config.enable_0to1 and not config.enable_1to0:
            self._service.stop()
        self._update_status()

    def enable_both(self):
        """Enable both directions."""
        self._enable_0to1.setChecked(True)
        self._enable_1to0.setChecked(True)

    def disable_both(self):
        """Disable both directions."""
        self._enable_0to1.setChecked(False)
        self._enable_1to0.setChecked(False)

    def _update_status(self):
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
        status_text = f"running (delay={delay}ms\u00b1{jitter}ms, loss={loss}%)"

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

    def update_status_text(self, status_text: str):
        """Update status text for running directions.

        Args:
            status_text: New status text to display
        """
        if self._service.is_running():
            if self._enable_0to1.isChecked():
                self._status_0to1.setText(f"running ({status_text})")
            if self._enable_1to0.isChecked():
                self._status_1to0.setText(f"running ({status_text})")

    def on_gateway_started(self, data):
        """Handle GATEWAY_STARTED event."""
        self._update_status()

    def on_gateway_stopped(self):
        """Handle GATEWAY_STOPPED event."""
        self._status_0to1.setText("stopped")
        self._status_0to1.setStyleSheet("color: #888;")
        self._status_1to0.setText("stopped")
        self._status_1to0.setStyleSheet("color: #888;")

    # Public API for testing
    @property
    def enable_0to1_checkbox(self) -> QCheckBox:
        """Get 0to1 enable checkbox."""
        return self._enable_0to1

    @property
    def enable_1to0_checkbox(self) -> QCheckBox:
        """Get 1to0 enable checkbox."""
        return self._enable_1to0

    @property
    def status_0to1_label(self) -> QLabel:
        """Get 0to1 status label."""
        return self._status_0to1

    @property
    def status_1to0_label(self) -> QLabel:
        """Get 1to0 status label."""
        return self._status_1to0

    def is_0to1_enabled(self) -> bool:
        """Check if 0to1 direction is enabled."""
        return self._enable_0to1.isChecked()

    def is_1to0_enabled(self) -> bool:
        """Check if 1to0 direction is enabled."""
        return self._enable_1to0.isChecked()


def create_gateway_group(
    iface0: str,
    iface1: str,
    service: GatewayService,
) -> tuple[QGroupBox, GatewayControlWidget]:
    """Create a gateway control group box.

    Args:
        iface0: First interface name
        iface1: Second interface name
        service: Gateway service instance

    Returns:
        Tuple of (QGroupBox, GatewayControlWidget)
    """
    group = QGroupBox("Gateway")
    widget = GatewayControlWidget(iface0, iface1, service)
    layout = QHBoxLayout(group)
    layout.addWidget(widget)
    return group, widget

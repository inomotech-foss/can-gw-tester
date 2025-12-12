"""Traffic Settings widget - delay, packet loss, and jitter controls.

Provides UI controls for traffic shaping parameters:
- Delay (ms)
- Packet loss (%)
- Jitter (ms)
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QWidget,
)

from wp4.services.gateway_service import GatewayService


class TrafficSettingsWidget(QWidget):
    """Widget for traffic control settings.

    Provides spinboxes for delay, packet loss, and jitter configuration.
    Validates input and warns about extreme values.
    """

    # Emitted when settings change
    settings_changed = Signal(int, float, float)  # delay_ms, loss_pct, jitter_ms

    def __init__(
        self,
        service: GatewayService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._service = service

        # Warning state tracking (to avoid repeated warnings)
        self._warned_high_loss = False
        self._warned_jitter_delay = False
        self._warned_high_delay = False

        self._setup_ui()

    def _setup_ui(self):
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Delay
        layout.addWidget(QLabel("Delay (ms):"), 0, 0)
        self._delay_spin = QSpinBox()
        self._delay_spin.setRange(0, 10000)
        self._delay_spin.setValue(0)
        self._delay_spin.setSuffix(" ms")
        self._delay_spin.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self._delay_spin, 0, 1)

        # Packet Loss
        layout.addWidget(QLabel("Packet Loss (%):"), 1, 0)
        self._loss_spin = QDoubleSpinBox()
        self._loss_spin.setRange(0.0, 100.0)
        self._loss_spin.setValue(0.0)
        self._loss_spin.setSingleStep(1.0)
        self._loss_spin.setDecimals(1)
        self._loss_spin.setSuffix(" %")
        self._loss_spin.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self._loss_spin, 1, 1)

        # Jitter
        layout.addWidget(QLabel("Jitter (\u00b1ms):"), 2, 0)
        self._jitter_spin = QDoubleSpinBox()
        self._jitter_spin.setRange(0.0, 1000.0)
        self._jitter_spin.setValue(0.0)
        self._jitter_spin.setSingleStep(1.0)
        self._jitter_spin.setDecimals(1)
        self._jitter_spin.setSuffix(" ms")
        self._jitter_spin.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self._jitter_spin, 2, 1)

    def _on_value_changed(self):
        """Handle any spinbox value change."""
        delay = self._delay_spin.value()
        loss = self._loss_spin.value()
        jitter = self._jitter_spin.value()

        # Validate and warn about extreme values
        self._check_extreme_values(delay, loss, jitter)

        # Update service
        self._service.update_settings(delay_ms=delay, loss_pct=loss, jitter_ms=jitter)

        # Emit signal
        self.settings_changed.emit(delay, loss, jitter)

    def _check_extreme_values(self, delay: int, loss: float, jitter: float):
        """Check for extreme values and warn user once per threshold crossing."""
        warnings = []

        # High packet loss warning (> 50%)
        if loss > 50 and not self._warned_high_loss:
            warnings.append(
                f"Packet loss {loss}% is very high!\nThis will cause significant data loss."
            )
            self._warned_high_loss = True
        elif loss <= 50:
            self._warned_high_loss = False

        # Jitter > delay warning
        if jitter > delay > 0 and not self._warned_jitter_delay:
            warnings.append(
                f"Jitter ({jitter}ms) is greater than delay ({delay}ms)!\n"
                "This may cause negative effective delays."
            )
            self._warned_jitter_delay = True
        elif jitter <= delay or delay == 0:
            self._warned_jitter_delay = False

        # Very high delay warning (> 5000ms)
        if delay > 5000 and not self._warned_high_delay:
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

    # Public API for external access
    def get_delay(self) -> int:
        """Get current delay value in milliseconds."""
        return self._delay_spin.value()

    def set_delay(self, value: int):
        """Set delay value in milliseconds."""
        self._delay_spin.setValue(value)

    def get_loss(self) -> float:
        """Get current packet loss percentage."""
        return self._loss_spin.value()

    def set_loss(self, value: float):
        """Set packet loss percentage."""
        self._loss_spin.setValue(value)

    def get_jitter(self) -> float:
        """Get current jitter value in milliseconds."""
        return self._jitter_spin.value()

    def set_jitter(self, value: float):
        """Set jitter value in milliseconds."""
        self._jitter_spin.setValue(value)

    def get_status_text(self) -> str:
        """Get formatted status text for current settings."""
        delay = self._delay_spin.value()
        loss = self._loss_spin.value()
        jitter = self._jitter_spin.value()
        return f"delay={delay}ms\u00b1{jitter}ms, loss={loss}%"

    # For testing
    @property
    def delay_spin(self) -> QSpinBox:
        """Get delay spinbox (for testing)."""
        return self._delay_spin

    @property
    def loss_spin(self) -> QDoubleSpinBox:
        """Get loss spinbox (for testing)."""
        return self._loss_spin

    @property
    def jitter_spin(self) -> QDoubleSpinBox:
        """Get jitter spinbox (for testing)."""
        return self._jitter_spin


def create_traffic_settings_group(
    service: GatewayService,
) -> tuple[QGroupBox, TrafficSettingsWidget]:
    """Create a traffic settings group box.

    Args:
        service: Gateway service instance

    Returns:
        Tuple of (QGroupBox, TrafficSettingsWidget)
    """
    group = QGroupBox("Traffic Control")
    widget = TrafficSettingsWidget(service)
    layout = QHBoxLayout(group)
    layout.addWidget(widget)
    return group, widget

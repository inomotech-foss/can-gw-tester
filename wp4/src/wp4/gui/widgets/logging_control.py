"""Logging Control widget - BLF logging and export.

Provides UI controls for:
- Enable/disable logging
- Log path selection
- Custom filename
- Export to ASC/log/analysis formats
"""

from pathlib import Path

from platformdirs import user_log_dir
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QWidget,
)

from wp4.services.gateway_service import GatewayService


class LoggingControlWidget(QWidget):
    """Widget for BLF logging control.

    Provides controls for enabling/disabling logging, selecting log path,
    and exporting to various formats.
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

        self._setup_ui()

    def _setup_ui(self):
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Enable checkbox
        self._log_enabled = QCheckBox("Enable Logging")
        self._log_enabled.stateChanged.connect(self._toggle_logging)
        layout.addWidget(self._log_enabled, 0, 0, 1, 3)

        # Log path
        layout.addWidget(QLabel("Log Path:"), 1, 0)
        self._log_path_edit = QLineEdit()
        default_log_path = Path(user_log_dir("wp4", ensure_exists=True))
        self._log_path_edit.setText(str(default_log_path))
        self._log_path_edit.setReadOnly(True)
        layout.addWidget(self._log_path_edit, 1, 1)

        self._log_browse_btn = QPushButton("Browse...")
        self._log_browse_btn.clicked.connect(self._browse_log_path)
        layout.addWidget(self._log_browse_btn, 1, 2)

        # Custom filename
        layout.addWidget(QLabel("Filename:"), 2, 0)
        self._log_name_edit = QLineEdit()
        self._log_name_edit.setPlaceholderText("(auto: gateway_YYYYMMDD_HHMMSS.blf)")
        self._log_name_edit.setToolTip(
            "Custom filename for the BLF log file.\n"
            "Leave empty for automatic timestamp-based naming.\n"
            "Extension .blf will be added automatically."
        )
        layout.addWidget(self._log_name_edit, 2, 1, 1, 2)

        # Active log file display
        self._log_files_label = QLabel("Active: --")
        self._log_files_label.setStyleSheet("font-family: monospace; font-size: 10px;")
        layout.addWidget(self._log_files_label, 3, 0, 1, 3)

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

        layout.addLayout(export_row, 4, 0, 1, 3)

    def _toggle_logging(self, state: int):
        """Toggle logging on/off."""
        if state:
            log_path = self._log_path_edit.text()
            log_name = self._log_name_edit.text().strip() or None
            self._service.set_log_path(log_path, custom_name=log_name)
            self._update_log_files_label()
        else:
            self._service.set_log_path(None)
            self._log_files_label.setText("Active: --")
            self._export_btn.setEnabled(False)

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
            if self._log_enabled.isChecked():
                self._service.set_log_path(path)
                self._update_log_files_label()

    def _update_log_files_label(self):
        """Update the log files label with current paths."""
        log_paths = self._service.get_log_paths()
        blf_path = log_paths.get("0to1")  # Both directions use same BLF file

        if blf_path and blf_path.exists():
            self._log_files_label.setText(f"Active: {blf_path.name}")
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

    def update_log_files_label(self):
        """Public method to update log files label (called when gateway starts)."""
        if self._log_enabled.isChecked():
            self._update_log_files_label()

    # Public API for testing
    @property
    def log_enabled(self) -> QCheckBox:
        """Get log enabled checkbox."""
        return self._log_enabled

    @property
    def log_path_edit(self) -> QLineEdit:
        """Get log path edit."""
        return self._log_path_edit

    @property
    def export_btn(self) -> QPushButton:
        """Get export active button."""
        return self._export_btn

    @property
    def export_file_btn(self) -> QPushButton:
        """Get export file button."""
        return self._export_file_btn

    def is_logging_enabled(self) -> bool:
        """Check if logging is enabled."""
        return self._log_enabled.isChecked()


def create_logging_group(
    iface0: str,
    iface1: str,
    service: GatewayService,
) -> tuple[QGroupBox, LoggingControlWidget]:
    """Create a logging control group box.

    Args:
        iface0: First interface name
        iface1: Second interface name
        service: Gateway service instance

    Returns:
        Tuple of (QGroupBox, LoggingControlWidget)
    """
    group = QGroupBox("Logging")
    widget = LoggingControlWidget(iface0, iface1, service)
    layout = QHBoxLayout(group)
    layout.addWidget(widget)
    return group, widget

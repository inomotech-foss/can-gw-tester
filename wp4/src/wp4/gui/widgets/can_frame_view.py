"""CAN Frame View widget - Display CAN messages from BLF files as tree.

Reads gateway BLF log files and displays them in a tree structure
grouped by message ID. Optimized for performance with large log files.

Uses a background thread for parsing to avoid blocking the GUI.
"""

from dataclasses import dataclass, field
from pathlib import Path

from platformdirs import user_log_dir
from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from wp4.services.gateway_service import GatewayService


@dataclass
class CanFrame:
    """A single CAN frame with metadata."""

    timestamp: float
    direction: str  # "0→1" or "1→0"
    arbitration_id: int
    data: bytes
    is_extended_id: bool
    dlc: int


@dataclass
class MessageGroup:
    """Group of frames with the same arbitration ID."""

    arbitration_id: int
    is_extended_id: bool
    frames: list[CanFrame] = field(default_factory=list)
    count_0to1: int = 0
    count_1to0: int = 0


class BLFParserWorker(QObject):
    """Background worker for parsing BLF files.

    Runs in a separate thread to avoid blocking the GUI.
    """

    finished = Signal(list)  # Emits list of CanFrame
    progress = Signal(int)  # Emits progress percentage
    error = Signal(str)  # Emits error message

    # Channel mapping (from GatewayLogger)
    CHANNEL_TO_DIRECTION = {
        1: "0→1",
        2: "1→0",
    }

    def __init__(self):
        super().__init__()
        self._blf_path: Path | None = None
        self._enable_0to1 = True
        self._enable_1to0 = True

    def set_file(
        self,
        blf_path: Path | None,
        enable_0to1: bool,
        enable_1to0: bool,
    ) -> None:
        """Set which file to parse and direction filters."""
        self._blf_path = blf_path
        self._enable_0to1 = enable_0to1
        self._enable_1to0 = enable_1to0

    def run(self) -> None:
        """Parse BLF file in background thread."""
        frames: list[CanFrame] = []

        if not self._blf_path or not self._blf_path.exists():
            self.finished.emit(frames)
            return

        self.progress.emit(0)

        try:
            from can.io.blf import BLFReader

            with BLFReader(str(self._blf_path)) as reader:
                msg_list = list(reader)

            total = len(msg_list)
            for i, msg in enumerate(msg_list):
                # Get direction from channel
                raw_ch = msg.channel
                if isinstance(raw_ch, int):
                    ch = raw_ch
                elif isinstance(raw_ch, str):
                    ch = int(raw_ch) if raw_ch.isdigit() else 0
                else:
                    ch = 0

                direction = self.CHANNEL_TO_DIRECTION.get(ch, f"CH{ch}")

                # Apply direction filter
                if ch == 1 and not self._enable_0to1:
                    continue
                if ch == 2 and not self._enable_1to0:
                    continue

                frame = CanFrame(
                    timestamp=msg.timestamp or 0.0,
                    direction=direction,
                    arbitration_id=msg.arbitration_id,
                    data=bytes(msg.data),
                    is_extended_id=msg.is_extended_id,
                    dlc=len(msg.data),
                )
                frames.append(frame)

                # Update progress every 1000 messages
                if i % 1000 == 0:
                    self.progress.emit(int(i / total * 100))

            self.progress.emit(100)

        except Exception as e:
            self.error.emit(str(e))

        self.finished.emit(frames)


class CanFrameViewWidget(QWidget):
    """Widget for viewing CAN frames from BLF files as tree structure.

    Features:
    - Reads BLF log files (industry standard)
    - Groups frames by message ID
    - Tree structure: ID -> individual frames
    - Direction filtering (0→1, 1→0)
    - Auto-refresh for live updates
    - Integrates with GatewayService for auto-detection
    """

    def __init__(
        self,
        iface0: str = "can0",
        iface1: str = "can1",
        service: GatewayService | None = None,
    ):
        super().__init__()
        self._iface0 = iface0
        self._iface1 = iface1
        self._service = service

        # BLF file path
        self._blf_path: Path | None = None

        # Message groups by ID
        self._groups: dict[int, MessageGroup] = {}
        self._frame_count = 0

        # Filter settings
        self._show_0to1 = True
        self._show_1to0 = True
        self._max_frames_per_id = 100

        # File modification tracking
        self._last_mtime = 0.0

        # Background parsing thread
        self._worker_thread: QThread | None = None
        self._worker: BLFParserWorker | None = None
        self._parsing_in_progress = False

        self._setup_ui()

        # Auto-refresh timer (check for file changes)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._check_for_updates)
        self._refresh_timer.start(1000)  # 1 Hz check

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # BLF file controls
        log_group = QGroupBox("BLF Log File")
        log_layout = QVBoxLayout(log_group)

        # File selection row
        file_row = QHBoxLayout()

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Select BLF file or use auto-detect...")
        self._path_edit.setReadOnly(True)
        file_row.addWidget(self._path_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_blf)
        file_row.addWidget(browse_btn)

        auto_btn = QPushButton("Auto")
        auto_btn.setToolTip("Auto-detect from gateway service")
        auto_btn.clicked.connect(self._auto_detect)
        file_row.addWidget(auto_btn)

        log_layout.addLayout(file_row)

        # Direction filters
        dir_row = QHBoxLayout()

        dir_row.addWidget(QLabel("Show:"))

        self._enable_0to1 = QCheckBox(f"{self._iface0}→{self._iface1}")
        self._enable_0to1.setChecked(True)
        self._enable_0to1.stateChanged.connect(self._reload_blf)
        dir_row.addWidget(self._enable_0to1)

        self._enable_1to0 = QCheckBox(f"{self._iface1}→{self._iface0}")
        self._enable_1to0.setChecked(True)
        self._enable_1to0.stateChanged.connect(self._reload_blf)
        dir_row.addWidget(self._enable_1to0)

        dir_row.addStretch()

        reload_btn = QPushButton("Reload")
        reload_btn.clicked.connect(self._reload_blf)
        dir_row.addWidget(reload_btn)

        log_layout.addLayout(dir_row)

        layout.addWidget(log_group)

        # Filter controls
        filter_group = QGroupBox("Display Options")
        filter_layout = QHBoxLayout(filter_group)

        filter_layout.addWidget(QLabel("Max frames/ID:"))
        self._max_frames_spin = QSpinBox()
        self._max_frames_spin.setRange(10, 10000)
        self._max_frames_spin.setValue(100)
        self._max_frames_spin.valueChanged.connect(self._rebuild_tree)
        filter_layout.addWidget(self._max_frames_spin)

        filter_layout.addStretch()

        # Progress bar (hidden by default)
        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximumWidth(100)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.hide()
        filter_layout.addWidget(self._progress_bar)

        # Frame count
        self._count_label = QLabel("0 frames")
        self._count_label.setStyleSheet("font-weight: bold;")
        filter_layout.addWidget(self._count_label)

        layout.addWidget(filter_group)

        # Tree widget
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["ID / Time", "Dir", "DLC", "Data", "ASCII"])
        self._tree.setAlternatingRowColors(True)
        self._tree.setStyleSheet("font-family: monospace;")

        # Column widths
        header = self._tree.header()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self._tree.setColumnWidth(0, 180)  # ID / Time
        self._tree.setColumnWidth(1, 60)  # Dir
        self._tree.setColumnWidth(2, 40)  # DLC
        self._tree.setColumnWidth(3, 220)  # Data
        self._tree.setColumnWidth(4, 100)  # ASCII

        layout.addWidget(self._tree)

        # Statistics
        stats_layout = QHBoxLayout()

        self._unique_ids_label = QLabel("0 unique IDs")
        stats_layout.addWidget(self._unique_ids_label)

        stats_layout.addStretch()

        self._count_0to1_label = QLabel(f"{self._iface0}→{self._iface1}: 0")
        self._count_0to1_label.setStyleSheet("color: #66ff66;")
        stats_layout.addWidget(self._count_0to1_label)

        self._count_1to0_label = QLabel(f"{self._iface1}→{self._iface0}: 0")
        self._count_1to0_label.setStyleSheet("color: #66ffff;")
        stats_layout.addWidget(self._count_1to0_label)

        layout.addLayout(stats_layout)

    def set_blf_path(self, path: Path | None) -> None:
        """Set BLF file path externally."""
        if path:
            self._blf_path = path
            self._path_edit.setText(str(path))
            self._last_mtime = 0.0
            self._reload_blf()

    def _browse_blf(self) -> None:
        """Browse for BLF file."""
        # Use same default path as logging section
        default_path = str(Path(user_log_dir("wp4", ensure_exists=True)))
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select BLF Log File",
            default_path,
            "BLF Files (*.blf);;All Files (*)",
        )
        if path:
            self.set_blf_path(Path(path))

    def _auto_detect(self) -> None:
        """Auto-detect BLF path from gateway service."""
        if self._service:
            log_paths = self._service.get_log_paths()
            blf_path = log_paths.get("0to1")  # Both directions in same file
            if blf_path and blf_path.exists():
                self.set_blf_path(blf_path)

    def _check_for_updates(self) -> None:
        """Check if BLF file has been modified."""
        if not self._blf_path or not self._blf_path.exists():
            return

        try:
            mtime = self._blf_path.stat().st_mtime
            if mtime > self._last_mtime:
                self._last_mtime = mtime
                self._reload_blf()
        except OSError:
            pass

    def _reload_blf(self) -> None:
        """Reload BLF file in background thread."""
        # Don't start new parsing if already in progress
        if self._parsing_in_progress:
            return

        if not self._blf_path or not self._blf_path.exists():
            self._groups.clear()
            self._frame_count = 0
            self._rebuild_tree()
            return

        self._parsing_in_progress = True
        self._progress_bar.setValue(0)
        self._progress_bar.show()
        self._count_label.setText("Loading...")

        # Clean up previous thread if exists
        if self._worker_thread is not None:
            self._worker_thread.quit()
            self._worker_thread.wait()

        # Create worker and thread
        self._worker_thread = QThread()
        self._worker = BLFParserWorker()
        self._worker.set_file(
            self._blf_path,
            self._enable_0to1.isChecked(),
            self._enable_1to0.isChecked(),
        )

        # Move worker to thread
        self._worker.moveToThread(self._worker_thread)

        # Connect signals
        self._worker_thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_parse_progress)
        self._worker.finished.connect(self._on_parse_finished)
        self._worker.finished.connect(self._worker_thread.quit)

        # Start thread
        self._worker_thread.start()

    def _on_parse_progress(self, percent: int) -> None:
        """Handle progress updates from worker."""
        self._progress_bar.setValue(percent)

    def _on_parse_finished(self, frames: list[CanFrame]) -> None:
        """Handle parsing completion."""
        self._parsing_in_progress = False
        self._progress_bar.hide()

        # Clear and rebuild groups
        self._groups.clear()
        self._frame_count = 0
        self._add_frames(frames)
        self._rebuild_tree()

    def _add_frames(self, frames: list[CanFrame]) -> None:
        """Add frames to groups."""
        for frame in frames:
            arb_id = frame.arbitration_id

            if arb_id not in self._groups:
                self._groups[arb_id] = MessageGroup(
                    arbitration_id=arb_id,
                    is_extended_id=frame.is_extended_id,
                )

            group = self._groups[arb_id]
            group.frames.append(frame)
            self._frame_count += 1

            if frame.direction == "0→1":
                group.count_0to1 += 1
            else:
                group.count_1to0 += 1

    def _rebuild_tree(self) -> None:
        """Rebuild tree widget from groups."""
        self._tree.clear()
        max_frames = self._max_frames_spin.value()

        # Sort groups by ID
        sorted_ids = sorted(self._groups.keys())

        total_0to1 = 0
        total_1to0 = 0

        for arb_id in sorted_ids:
            group = self._groups[arb_id]

            if not group.frames:
                continue

            # Limit frames per ID (most recent)
            limited_frames = group.frames[-max_frames:]

            # Create parent item for this ID
            id_str = f"0x{arb_id:08X}" if group.is_extended_id else f"0x{arb_id:03X}"
            parent = QTreeWidgetItem(
                [
                    f"{id_str} ({len(group.frames)} frames)",
                    "",
                    "",
                    f"0→1:{group.count_0to1}  1→0:{group.count_1to0}",
                    "",
                ]
            )
            parent.setExpanded(False)

            # Color based on direction mix
            if group.count_0to1 > 0 and group.count_1to0 > 0:
                parent.setForeground(0, QBrush(QColor("#ffff66")))  # Both
            elif group.count_0to1 > 0:
                parent.setForeground(0, QBrush(QColor("#66ff66")))  # 0→1
            else:
                parent.setForeground(0, QBrush(QColor("#66ffff")))  # 1→0

            # Add child items (most recent first)
            for frame in reversed(limited_frames):
                ts_str = f"{frame.timestamp:.6f}"
                data_hex = " ".join(f"{b:02X}" for b in frame.data)
                ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in frame.data)

                child = QTreeWidgetItem(
                    [
                        ts_str,
                        frame.direction,
                        str(frame.dlc),
                        data_hex,
                        ascii_str,
                    ]
                )

                # Color by direction
                if frame.direction == "0→1":
                    child.setForeground(1, QBrush(QColor("#66ff66")))
                else:
                    child.setForeground(1, QBrush(QColor("#66ffff")))

                parent.addChild(child)

            self._tree.addTopLevelItem(parent)

            total_0to1 += group.count_0to1
            total_1to0 += group.count_1to0

        # Update statistics
        self._count_label.setText(f"{self._frame_count:,} frames")
        self._unique_ids_label.setText(f"{len(self._groups)} unique IDs")
        self._count_0to1_label.setText(f"{self._iface0}→{self._iface1}: {total_0to1:,}")
        self._count_1to0_label.setText(f"{self._iface1}→{self._iface0}: {total_1to0:,}")

    def refresh(self) -> None:
        """Force refresh (public API)."""
        self._last_mtime = 0.0
        self._reload_blf()

    def stop(self) -> None:
        """Stop timers and threads (cleanup)."""
        if self._refresh_timer:
            self._refresh_timer.stop()

        # Clean up worker thread
        if self._worker_thread is not None:
            self._worker_thread.quit()
            self._worker_thread.wait(1000)  # Wait max 1 second
            self._worker_thread = None
            self._worker = None

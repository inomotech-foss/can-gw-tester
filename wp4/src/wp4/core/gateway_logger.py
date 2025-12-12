"""BLF-based gateway logger for CAN message capture.

Uses python-can's BLFWriter for efficient, compressed logging.
BLF (Binary Logging Format) is an industry-standard format that:
- Is compressed (~10x smaller than text logs)
- Can be imported directly into CANalyzer/CANoe
- Supports timing-accurate replay via MessageSync
- Natively supports CAN FD frames
"""

import time
from datetime import datetime
from pathlib import Path

import can
from can.io.blf import BLFWriter


class GatewayLogger:
    """Logs CAN messages to BLF (Binary Logging Format).

    Uses python-can's BLFWriter for efficient, compressed logging.
    Direction is encoded in the channel field:
    - Channel 1: Direction 0→1
    - Channel 2: Direction 1→0

    Usage:
        logger = GatewayLogger(Path("logs"))
        logger.start("vcan0", "vcan1")

        # Log messages
        logger.log_rx("0to1", msg)
        logger.log_tx("0to1", msg, latency_us=1234.5)
        logger.log_drop("1to0", msg)

        logger.stop()

    The resulting BLF file can be:
    - Imported into CANalyzer/CANoe
    - Converted to ASC format via LogExporter
    - Replayed with original timing via MessageSync
    """

    CHANNEL_MAP = {
        "0to1": 1,  # Direction 0→1 uses channel 1
        "1to0": 2,  # Direction 1→0 uses channel 2
    }

    def __init__(self, base_path: Path | str | None = None):
        """Initialize gateway logger.

        Args:
            base_path: Base directory for log files. If None, logging is disabled.
        """
        self._base_path = Path(base_path) if base_path else None
        self._writer: BLFWriter | None = None
        self._enabled = False
        self._start_time: float | None = None
        self._blf_path: Path | None = None
        self._iface0: str = ""
        self._iface1: str = ""

    def set_log_path(self, path: Path | str | None) -> None:
        """Set or change the log path."""
        self._base_path = Path(path) if path else None

    def start(self, iface0: str, iface1: str, custom_name: str | None = None) -> None:
        """Start logging to BLF file.

        Args:
            iface0: Name of first interface (e.g., "vcan0")
            iface1: Name of second interface (e.g., "vcan1")
            custom_name: Optional custom filename (without extension).
                         If None, uses automatic timestamp-based naming.
        """
        if self._base_path is None:
            return

        self._iface0 = iface0
        self._iface1 = iface1

        self._base_path.mkdir(parents=True, exist_ok=True)

        # Use custom name or generate timestamp-based name
        if custom_name:
            # Ensure .blf extension
            filename = f"{custom_name}.blf" if not custom_name.endswith(".blf") else custom_name
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"gateway_{iface0}_{iface1}_{timestamp}.blf"

        self._blf_path = self._base_path / filename

        self._writer = BLFWriter(str(self._blf_path))
        self._start_time = time.time()
        self._enabled = True

    def stop(self) -> None:
        """Stop logging and close BLF file."""
        self._enabled = False
        if self._writer:
            self._writer.stop()
            self._writer = None

    def flush(self) -> None:
        """Flush buffered data to disk.

        Note: BLFWriter handles buffering internally, this is a no-op
        but kept for API compatibility.
        """
        pass

    def _log_message(self, direction: str, msg: can.Message) -> None:
        """Internal method to log a CAN message to BLF.

        Args:
            direction: "0to1" or "1to0"
            msg: The CAN message to log
        """
        if not self._enabled or not self._writer:
            return

        # Set channel based on direction
        msg.channel = self.CHANNEL_MAP.get(direction, 1)

        # Set relative timestamp from start
        if self._start_time:
            msg.timestamp = time.time() - self._start_time

        # Write message to BLF
        self._writer.on_message_received(msg)

    def log_rx(
        self,
        direction: str,
        timestamp: float,
        arb_id: int,
        data: bytes,
        is_extended: bool,
    ) -> None:
        """Log RX (receive) event.

        Args:
            direction: "0to1" or "1to0"
            timestamp: Reception timestamp (time.time() value)
            arb_id: CAN arbitration ID
            data: Message data bytes
            is_extended: True if extended CAN ID
        """
        if not self._enabled or not self._writer:
            return

        msg = can.Message(
            arbitration_id=arb_id,
            data=data,
            is_extended_id=is_extended,
            channel=self.CHANNEL_MAP.get(direction, 1),
        )

        # Set relative timestamp
        if self._start_time:
            msg.timestamp = timestamp - self._start_time

        self._writer.on_message_received(msg)

    def log_queue(
        self,
        direction: str,
        timestamp: float,
        arb_id: int,
        data: bytes,
        is_extended: bool,
        scheduled_time: float,
    ) -> None:
        """Log QUEUE event (message queued for delayed send).

        Note: BLF format doesn't have a native "queue" event type.
        This is logged as a regular message - the delay information
        is implicit from the time difference between RX and TX events.

        Args:
            direction: "0to1" or "1to0"
            timestamp: Queue timestamp
            arb_id: CAN arbitration ID
            data: Message data bytes
            is_extended: True if extended CAN ID
            scheduled_time: When the message is scheduled to be sent
        """
        # QUEUE events are not logged in BLF - the delay is visible
        # from the time difference between RX and TX events
        pass

    def log_tx(
        self,
        direction: str,
        timestamp: float,
        arb_id: int,
        data: bytes,
        is_extended: bool,
        latency_us: float,
    ) -> None:
        """Log TX (transmit) event.

        Args:
            direction: "0to1" or "1to0"
            timestamp: Transmission timestamp (time.time() value)
            arb_id: CAN arbitration ID
            data: Message data bytes
            is_extended: True if extended CAN ID
            latency_us: Actual latency in microseconds (for statistics)
        """
        if not self._enabled or not self._writer:
            return

        msg = can.Message(
            arbitration_id=arb_id,
            data=data,
            is_extended_id=is_extended,
            channel=self.CHANNEL_MAP.get(direction, 1),
        )

        # Set relative timestamp
        if self._start_time:
            msg.timestamp = timestamp - self._start_time

        self._writer.on_message_received(msg)

    def log_drop(
        self,
        direction: str,
        timestamp: float,
        arb_id: int,
        data: bytes,
        is_extended: bool,
    ) -> None:
        """Log DROP event (message dropped due to packet loss or queue overflow).

        Note: BLF doesn't have a native "drop" marker. Dropped messages
        are simply not present in the log. For analysis, compare RX count
        with TX count to determine drop rate.

        Args:
            direction: "0to1" or "1to0"
            timestamp: Drop timestamp
            arb_id: CAN arbitration ID
            data: Message data bytes
            is_extended: True if extended CAN ID
        """
        # DROP events are not logged - they're implicit from missing TX
        pass

    @property
    def is_enabled(self) -> bool:
        """Check if logging is enabled."""
        return self._enabled

    def get_blf_path(self) -> Path | None:
        """Get path to current BLF file."""
        return self._blf_path

    def get_log_paths(self) -> dict[str, Path | None]:
        """Get log file paths (for API compatibility).

        Returns:
            Dictionary with '0to1' and '1to0' keys mapping to the same BLF path
        """
        return {
            "0to1": self._blf_path,
            "1to0": self._blf_path,
        }

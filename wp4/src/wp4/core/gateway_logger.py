"""BLF and CSV gateway logger for CAN message capture.

Uses python-can's BLFWriter for efficient, compressed logging.
BLF (Binary Logging Format) is an industry-standard format that:
- Is compressed (~10x smaller than text logs)
- Can be imported directly into CANalyzer/CANoe
- Supports timing-accurate replay via MessageSync
- Natively supports CAN FD frames

Additionally writes a CSV file with gateway-specific metadata:
- RX/TX timestamps, latency, drop status
- Configured delay, jitter, and loss percentage per message
"""

import csv
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO

import can
from can.io.blf import BLFWriter


@dataclass
class GatewayConfig:
    """Gateway configuration for CSV logging."""

    delay_ms: float = 0.0
    jitter_ms: float = 0.0
    loss_pct: float = 0.0


class GatewayLogger:
    """Logs CAN messages to BLF and CSV formats.

    BLF: Industry-standard format for CANalyzer/CANoe compatibility.
    CSV: Gateway-specific metadata (latency, drop status, config).

    Direction is encoded in the channel field:
    - Channel 1: Direction 0→1
    - Channel 2: Direction 1→0

    Usage:
        logger = GatewayLogger(Path("logs"))
        logger.set_gateway_config(delay_ms=50, jitter_ms=10, loss_pct=5.0)
        logger.start("vcan0", "vcan1")

        # Log messages (both BLF and CSV are written)
        logger.log_rx("0to1", timestamp, arb_id, data, is_extended)
        logger.log_tx("0to1", timestamp, arb_id, data, is_extended, latency_us)
        logger.log_drop("1to0", timestamp, arb_id, data, is_extended)

        logger.stop()

    Output files:
    - gateway_vcan0_vcan1_YYYYMMDD_HHMMSS.blf (CAN messages)
    - gateway_vcan0_vcan1_YYYYMMDD_HHMMSS.csv (metadata)
    """

    CHANNEL_MAP = {
        "0to1": 1,  # Direction 0→1 uses channel 1
        "1to0": 2,  # Direction 1→0 uses channel 2
    }

    CSV_COLUMNS = [
        "seq",
        "event",
        "direction",
        "rx_ts",
        "tx_ts",
        "arb_id",
        "dlc",
        "data",
        "delay_ms",
        "jitter_ms",
        "loss_pct",
        "latency_us",
    ]

    def __init__(self, base_path: Path | str | None = None):
        """Initialize gateway logger.

        Args:
            base_path: Base directory for log files. If None, logging is disabled.
        """
        self._base_path = Path(base_path) if base_path else None
        self._writer: BLFWriter | None = None
        self._csv_file: TextIO | None = None
        self._csv_writer: csv.DictWriter | None = None
        self._enabled = False
        self._start_time: float | None = None
        self._blf_path: Path | None = None
        self._csv_path: Path | None = None
        self._iface0: str = ""
        self._iface1: str = ""
        self._seq: int = 0
        self._config = GatewayConfig()

    def set_log_path(self, path: Path | str | None) -> None:
        """Set or change the log path."""
        self._base_path = Path(path) if path else None

    def set_gateway_config(
        self, delay_ms: float = 0.0, jitter_ms: float = 0.0, loss_pct: float = 0.0
    ) -> None:
        """Set gateway configuration for CSV logging.

        Call this before start() or dynamically update during logging.
        The current config values are written to each CSV row.

        Args:
            delay_ms: Configured delay in milliseconds
            jitter_ms: Configured jitter in milliseconds
            loss_pct: Configured packet loss percentage
        """
        self._config = GatewayConfig(delay_ms=delay_ms, jitter_ms=jitter_ms, loss_pct=loss_pct)

    def start(self, iface0: str, iface1: str, custom_name: str | None = None) -> None:
        """Start logging to BLF and CSV files.

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
        self._seq = 0

        self._base_path.mkdir(parents=True, exist_ok=True)

        # Use custom name or generate timestamp-based name
        if custom_name:
            # Remove extension if present
            base_name = custom_name.removesuffix(".blf").removesuffix(".csv")
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = f"gateway_{iface0}_{iface1}_{timestamp}"

        self._blf_path = self._base_path / f"{base_name}.blf"
        self._csv_path = self._base_path / f"{base_name}.csv"

        # Start BLF writer
        self._writer = BLFWriter(str(self._blf_path))

        # Start CSV writer
        self._csv_file = self._csv_path.open("w", newline="", encoding="utf-8")
        self._csv_writer = csv.DictWriter(self._csv_file, fieldnames=self.CSV_COLUMNS)
        self._csv_writer.writeheader()

        self._start_time = time.time()
        self._enabled = True

    def stop(self) -> None:
        """Stop logging and close BLF and CSV files."""
        self._enabled = False
        if self._writer:
            self._writer.stop()
            self._writer = None
        if self._csv_file:
            self._csv_file.close()
            self._csv_file = None
            self._csv_writer = None

    def flush(self) -> None:
        """Flush buffered data to disk."""
        if self._csv_file:
            self._csv_file.flush()

    def _format_arb_id(self, arb_id: int, is_extended: bool) -> str:
        """Format arbitration ID as hex string."""
        if is_extended:
            return f"0x{arb_id:08X}"
        return f"0x{arb_id:03X}"

    def _format_data(self, data: bytes) -> str:
        """Format data bytes as hex string."""
        return " ".join(f"{b:02X}" for b in data)

    def _write_csv_row(
        self,
        event: str,
        direction: str,
        rx_ts: float | None,
        tx_ts: float | None,
        arb_id: int,
        data: bytes,
        is_extended: bool,
        latency_us: float | None = None,
    ) -> None:
        """Write a row to the CSV file.

        Args:
            event: Event type ("forwarded" or "dropped")
            direction: "0to1" or "1to0"
            rx_ts: Receive timestamp (absolute time.time() value)
            tx_ts: Transmit timestamp (absolute), None for dropped messages
            arb_id: CAN arbitration ID
            data: Message data bytes
            is_extended: True if extended CAN ID
            latency_us: Actual latency in microseconds, None for dropped
        """
        if not self._csv_writer or not self._start_time:
            return

        self._seq += 1

        # Convert absolute timestamps to relative (from start)
        rx_rel = f"{rx_ts - self._start_time:.6f}" if rx_ts else ""
        tx_rel = f"{tx_ts - self._start_time:.6f}" if tx_ts else ""

        row = {
            "seq": self._seq,
            "event": event,
            "direction": direction,
            "rx_ts": rx_rel,
            "tx_ts": tx_rel,
            "arb_id": self._format_arb_id(arb_id, is_extended),
            "dlc": len(data),
            "data": self._format_data(data),
            "delay_ms": f"{self._config.delay_ms:.1f}",
            "jitter_ms": f"{self._config.jitter_ms:.1f}",
            "loss_pct": f"{self._config.loss_pct:.1f}",
            "latency_us": f"{latency_us:.1f}" if latency_us is not None else "",
        }
        self._csv_writer.writerow(row)

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
        """Log TX (transmit) event to BLF and CSV.

        Args:
            direction: "0to1" or "1to0"
            timestamp: Transmission timestamp (time.time() value)
            arb_id: CAN arbitration ID
            data: Message data bytes
            is_extended: True if extended CAN ID
            latency_us: Actual latency in microseconds (for statistics)
        """
        if not self._enabled:
            return

        # Calculate RX timestamp from TX timestamp and latency
        rx_timestamp = timestamp - (latency_us / 1_000_000)

        # Write to BLF
        if self._writer:
            msg = can.Message(
                arbitration_id=arb_id,
                data=data,
                is_extended_id=is_extended,
                channel=self.CHANNEL_MAP.get(direction, 1),
            )
            if self._start_time:
                msg.timestamp = timestamp - self._start_time
            self._writer.on_message_received(msg)

        # Write to CSV
        self._write_csv_row(
            event="forwarded",
            direction=direction,
            rx_ts=rx_timestamp,
            tx_ts=timestamp,
            arb_id=arb_id,
            data=data,
            is_extended=is_extended,
            latency_us=latency_us,
        )

    def log_drop(
        self,
        direction: str,
        timestamp: float,
        arb_id: int,
        data: bytes,
        is_extended: bool,
    ) -> None:
        """Log DROP event to CSV (message dropped due to packet loss or rule).

        Note: BLF doesn't have a native "drop" marker, so dropped messages
        are only logged to CSV where they can be analyzed.

        Args:
            direction: "0to1" or "1to0"
            timestamp: Drop timestamp (= RX timestamp)
            arb_id: CAN arbitration ID
            data: Message data bytes
            is_extended: True if extended CAN ID
        """
        if not self._enabled:
            return

        # Write to CSV only (BLF doesn't support drop markers)
        self._write_csv_row(
            event="dropped",
            direction=direction,
            rx_ts=timestamp,
            tx_ts=None,
            arb_id=arb_id,
            data=data,
            is_extended=is_extended,
            latency_us=None,
        )

    @property
    def is_enabled(self) -> bool:
        """Check if logging is enabled."""
        return self._enabled

    def get_blf_path(self) -> Path | None:
        """Get path to current BLF file."""
        return self._blf_path

    def get_csv_path(self) -> Path | None:
        """Get path to current CSV file."""
        return self._csv_path

    def get_log_paths(self) -> dict[str, Path | None]:
        """Get all log file paths.

        Returns:
            Dictionary with paths to all log files:
            - 'blf': Path to BLF file (CAN messages for CANalyzer)
            - 'csv': Path to CSV file (gateway metadata)
            - '0to1', '1to0': Same as 'blf' (for backward compatibility)
        """
        return {
            "blf": self._blf_path,
            "csv": self._csv_path,
            "0to1": self._blf_path,
            "1to0": self._blf_path,
        }

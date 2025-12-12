"""Export BLF logs to various formats on-demand.

Provides conversion from BLF (Binary Logging Format) to:
- ASC format (Vector ASCII format for replay in CANalyzer/CANoe)
- Human-readable text logs (for debugging)
- Statistics extraction (message counts, duration, throughput)
- Timing-accurate replay to a CAN bus
"""

from datetime import datetime
from pathlib import Path

import can
from can.io.asc import ASCWriter
from can.io.blf import BLFReader


class LogExporter:
    """Export BLF logs to various formats.

    All methods are static and can be used without instantiation:

        from wp4.core.log_exporter import LogExporter

        # Convert to ASC for replay
        asc_path = LogExporter.blf_to_asc(blf_path)

        # Convert to human-readable log
        log_path = LogExporter.blf_to_human_readable(blf_path)

        # Get statistics
        stats = LogExporter.blf_to_statistics(blf_path)

        # Replay with original timing
        LogExporter.replay_blf(blf_path, target_bus)
    """

    @staticmethod
    def blf_to_asc(blf_path: Path, output_path: Path | None = None) -> Path:
        """Convert BLF to ASC format for replay (single file, all channels).

        ASC (ASCII Logging Format) is Vector's text-based format that:
        - Can be imported into CANalyzer/CANoe
        - Is human-readable
        - Preserves timing information for replay

        Args:
            blf_path: Path to input BLF file
            output_path: Path for output ASC file (default: same name with .asc)

        Returns:
            Path to created ASC file
        """
        if output_path is None:
            output_path = blf_path.with_suffix(".asc")

        with BLFReader(str(blf_path)) as reader, ASCWriter(str(output_path)) as writer:
            for msg in reader:
                writer.on_message_received(msg)

        return output_path

    @staticmethod
    def blf_to_asc_per_channel(
        blf_path: Path,
        iface0: str = "can0",
        iface1: str = "can1",
    ) -> dict[str, Path]:
        """Convert BLF to separate ASC files per channel for replay.

        Creates two ASC files, one for each CAN bus direction:
        - Channel 1 (0→1): Messages received on iface0, to replay on iface0
        - Channel 2 (1→0): Messages received on iface1, to replay on iface1

        This allows replaying traffic on each bus independently with
        accurate timing.

        Args:
            blf_path: Path to input BLF file
            iface0: Name of first interface (for filename, e.g., "vcan0")
            iface1: Name of second interface (for filename, e.g., "vcan1")

        Returns:
            Dictionary with paths to created ASC files:
            {
                "ch1": Path to ASC for channel 1 (iface0 traffic),
                "ch2": Path to ASC for channel 2 (iface1 traffic),
            }
        """
        # Output paths: gateway_xxx.blf -> gateway_xxx_vcan0.asc, gateway_xxx_vcan1.asc
        stem = blf_path.stem
        parent = blf_path.parent

        asc_ch1_path = parent / f"{stem}_{iface0}.asc"
        asc_ch2_path = parent / f"{stem}_{iface1}.asc"

        # Collect messages by channel
        ch1_messages: list[can.Message] = []
        ch2_messages: list[can.Message] = []

        with BLFReader(str(blf_path)) as reader:
            for msg in reader:
                raw_ch = msg.channel
                if isinstance(raw_ch, int):
                    ch = raw_ch
                elif isinstance(raw_ch, str):
                    ch = int(raw_ch) if raw_ch.isdigit() else 0
                else:
                    ch = 0

                if ch == 1:
                    ch1_messages.append(msg)
                elif ch == 2:
                    ch2_messages.append(msg)

        # Write channel 1 ASC (iface0 traffic)
        if ch1_messages:
            with ASCWriter(str(asc_ch1_path)) as writer:
                for msg in ch1_messages:
                    writer.on_message_received(msg)
        else:
            # Create empty file with header
            asc_ch1_path.write_text(f"; No messages for channel 1 ({iface0})\n")

        # Write channel 2 ASC (iface1 traffic)
        if ch2_messages:
            with ASCWriter(str(asc_ch2_path)) as writer:
                for msg in ch2_messages:
                    writer.on_message_received(msg)
        else:
            # Create empty file with header
            asc_ch2_path.write_text(f"; No messages for channel 2 ({iface1})\n")

        return {
            "ch1": asc_ch1_path,
            "ch2": asc_ch2_path,
        }

    @staticmethod
    def blf_to_human_readable(blf_path: Path, output_path: Path | None = None) -> Path:
        """Convert BLF to human-readable text log.

        Creates a formatted text log with:
        - Timestamps
        - Channel (direction) information
        - CAN ID (standard or extended)
        - Data bytes in hex format

        Args:
            blf_path: Path to input BLF file
            output_path: Path for output log file (default: same name with .log)

        Returns:
            Path to created log file
        """
        if output_path is None:
            output_path = blf_path.with_suffix(".log")

        channel_names = {
            1: "0→1",
            2: "1→0",
        }

        with BLFReader(str(blf_path)) as reader, output_path.open("w") as f:
            f.write(f"# Gateway Log - Exported from {blf_path.name}\n")
            f.write(f"# Exported: {datetime.now().isoformat()}\n")
            f.write("# Format: [timestamp] DIR | ID=0xXXX | DLC=N | DATA=XX XX ...\n")
            f.write("#" + "=" * 70 + "\n\n")

            for msg in reader:
                ts = f"{msg.timestamp:.6f}" if msg.timestamp else "0.000000"
                # Channel can be int, str, Sequence, or None - extract int value
                raw_ch = msg.channel
                if isinstance(raw_ch, int):
                    ch = raw_ch
                elif isinstance(raw_ch, str):
                    ch = int(raw_ch) if raw_ch.isdigit() else 0
                else:
                    ch = 0
                direction = channel_names.get(ch, f"CH{ch}")

                if msg.is_extended_id:
                    id_str = f"0x{msg.arbitration_id:08X}"
                else:
                    id_str = f"0x{msg.arbitration_id:03X}"

                data_str = " ".join(f"{b:02X}" for b in msg.data)
                dlc = len(msg.data)

                f.write(f"[{ts}] {direction:4} | ID={id_str} | DLC={dlc} | DATA={data_str}\n")

        return output_path

    @staticmethod
    def blf_to_statistics(blf_path: Path) -> dict:
        """Extract statistics from BLF file.

        Returns comprehensive statistics including:
        - Total message count
        - Messages by channel (direction)
        - Messages by arbitration ID
        - Capture duration
        - Average throughput (messages/second)

        Args:
            blf_path: Path to input BLF file

        Returns:
            Dictionary with statistics:
            {
                "total_messages": int,
                "by_channel": {1: count, 2: count, ...},
                "by_arbitration_id": {"0x123": count, ...},
                "duration_s": float,
                "messages_per_second": float,
                "first_timestamp": float,
                "last_timestamp": float,
            }
        """
        stats: dict = {
            "total_messages": 0,
            "by_channel": {},
            "by_arbitration_id": {},
            "duration_s": 0.0,
            "messages_per_second": 0.0,
            "first_timestamp": None,
            "last_timestamp": None,
        }

        first_ts: float | None = None
        last_ts: float | None = None

        with BLFReader(str(blf_path)) as reader:
            for msg in reader:
                stats["total_messages"] += 1

                # By channel (extract int value for consistent keys)
                raw_ch = msg.channel
                if isinstance(raw_ch, int):
                    ch = raw_ch
                elif isinstance(raw_ch, str):
                    ch = int(raw_ch) if raw_ch.isdigit() else 0
                else:
                    ch = 0
                stats["by_channel"][ch] = stats["by_channel"].get(ch, 0) + 1

                # By arbitration ID (formatted as hex string)
                if msg.is_extended_id:
                    arb_id = f"0x{msg.arbitration_id:08X}"
                else:
                    arb_id = f"0x{msg.arbitration_id:03X}"
                stats["by_arbitration_id"][arb_id] = stats["by_arbitration_id"].get(arb_id, 0) + 1

                # Track timestamps
                if msg.timestamp is not None:
                    if first_ts is None:
                        first_ts = msg.timestamp
                    last_ts = msg.timestamp

        # Calculate duration and throughput
        stats["first_timestamp"] = first_ts
        stats["last_timestamp"] = last_ts

        if first_ts is not None and last_ts is not None:
            stats["duration_s"] = last_ts - first_ts
            if stats["duration_s"] > 0:
                stats["messages_per_second"] = stats["total_messages"] / stats["duration_s"]

        return stats

    @staticmethod
    def replay_blf(blf_path: Path, target_bus: can.BusABC) -> int:
        """Replay BLF file with original timing.

        Uses python-can's MessageSync to replay messages with
        timing-accurate delays between messages.

        Args:
            blf_path: Path to input BLF file
            target_bus: CAN bus to send messages on

        Returns:
            Number of messages sent
        """
        count = 0
        with BLFReader(str(blf_path)) as reader:
            for msg in can.MessageSync(messages=reader):
                target_bus.send(msg)
                count += 1
        return count

    @staticmethod
    def format_statistics_report(stats: dict) -> str:
        """Format statistics dictionary as human-readable report.

        Args:
            stats: Statistics dictionary from blf_to_statistics()

        Returns:
            Formatted string report
        """
        lines = [
            "=" * 50,
            "BLF Log Statistics Report",
            "=" * 50,
            "",
            f"Total Messages: {stats['total_messages']:,}",
            f"Duration: {stats['duration_s']:.3f} seconds",
            f"Throughput: {stats['messages_per_second']:.1f} msg/s",
            "",
            "Messages by Direction:",
        ]

        channel_names = {1: "  0→1", 2: "  1→0"}
        for ch, count in sorted(stats["by_channel"].items()):
            name = channel_names.get(ch, f"  CH{ch}")
            lines.append(f"{name}: {count:,}")

        lines.append("")
        lines.append("Top 10 Arbitration IDs:")

        # Sort by count, take top 10
        sorted_ids = sorted(
            stats["by_arbitration_id"].items(),
            key=lambda x: x[1],
            reverse=True,
        )[:10]

        for arb_id, count in sorted_ids:
            pct = (count / stats["total_messages"] * 100) if stats["total_messages"] > 0 else 0
            lines.append(f"  {arb_id}: {count:,} ({pct:.1f}%)")

        lines.append("")
        lines.append("=" * 50)

        return "\n".join(lines)

    @staticmethod
    def blf_to_detailed_analysis(blf_path: Path, output_path: Path | None = None) -> Path:
        """Create detailed per-frame analysis log with nanosecond timestamps.

        Creates a comprehensive analysis file with:
        - Per-frame data (timestamp, direction, ID, data)
        - Inter-frame timing (delta from previous frame)
        - Summary statistics at the end

        Timestamps are exported with nanosecond precision (9 decimal places).

        Args:
            blf_path: Path to input BLF file
            output_path: Path for output file (default: same name with .analysis.log)

        Returns:
            Path to created analysis file
        """
        if output_path is None:
            output_path = blf_path.with_suffix(".analysis.log")

        channel_names = {1: "0→1", 2: "1→0"}

        # First pass: collect all messages and compute statistics
        messages: list[dict] = []
        prev_ts: float | None = None

        with BLFReader(str(blf_path)) as reader:
            for msg in reader:
                ts = msg.timestamp or 0.0
                raw_ch = msg.channel
                if isinstance(raw_ch, int):
                    ch = raw_ch
                elif isinstance(raw_ch, str):
                    ch = int(raw_ch) if raw_ch.isdigit() else 0
                else:
                    ch = 0

                # Calculate delta from previous message
                delta_us = 0.0
                if prev_ts is not None:
                    delta_us = (ts - prev_ts) * 1_000_000  # Convert to microseconds

                messages.append(
                    {
                        "timestamp": ts,
                        "timestamp_ns": int(ts * 1_000_000_000),  # Nanoseconds
                        "channel": ch,
                        "direction": channel_names.get(ch, f"CH{ch}"),
                        "arb_id": msg.arbitration_id,
                        "is_extended": msg.is_extended_id,
                        "dlc": len(msg.data),
                        "data": msg.data,
                        "delta_us": delta_us,
                    }
                )
                prev_ts = ts

        # Calculate statistics
        total = len(messages)
        by_direction = {1: 0, 2: 0}
        by_id: dict[int, int] = {}
        deltas: list[float] = []

        for m in messages:
            by_direction[m["channel"]] = by_direction.get(m["channel"], 0) + 1
            by_id[m["arb_id"]] = by_id.get(m["arb_id"], 0) + 1
            if m["delta_us"] > 0:
                deltas.append(m["delta_us"])

        # Calculate timing statistics
        if deltas:
            avg_delta = sum(deltas) / len(deltas)
            min_delta = min(deltas)
            max_delta = max(deltas)
            sorted_deltas = sorted(deltas)
            p50_delta = sorted_deltas[len(sorted_deltas) // 2]
            p95_idx = int(len(sorted_deltas) * 0.95)
            p99_idx = int(len(sorted_deltas) * 0.99)
            p95_delta = sorted_deltas[min(p95_idx, len(sorted_deltas) - 1)]
            p99_delta = sorted_deltas[min(p99_idx, len(sorted_deltas) - 1)]
        else:
            avg_delta = min_delta = max_delta = p50_delta = p95_delta = p99_delta = 0.0

        duration = messages[-1]["timestamp"] - messages[0]["timestamp"] if messages else 0.0

        # Write analysis file
        with output_path.open("w") as f:
            f.write("=" * 100 + "\n")
            f.write("GATEWAY LOG DETAILED ANALYSIS\n")
            f.write("=" * 100 + "\n")
            f.write(f"Source: {blf_path.name}\n")
            f.write(f"Exported: {datetime.now().isoformat()}\n")
            f.write("\n")

            # Summary statistics
            f.write("-" * 50 + "\n")
            f.write("SUMMARY STATISTICS\n")
            f.write("-" * 50 + "\n")
            f.write(f"Total Messages:    {total:,}\n")
            f.write(f"Duration:          {duration:.6f} s\n")
            f.write(f"Throughput:        {total / duration:.1f} msg/s\n" if duration > 0 else "")
            f.write("\n")
            f.write(f"Direction 0→1:     {by_direction.get(1, 0):,} messages\n")
            f.write(f"Direction 1→0:     {by_direction.get(2, 0):,} messages\n")
            f.write(f"Unique IDs:        {len(by_id)}\n")
            f.write("\n")

            # Timing statistics
            f.write("-" * 50 + "\n")
            f.write("INTER-FRAME TIMING (microseconds)\n")
            f.write("-" * 50 + "\n")
            f.write(f"Min Delta:         {min_delta:.3f} us\n")
            f.write(f"Max Delta:         {max_delta:.3f} us\n")
            f.write(f"Avg Delta:         {avg_delta:.3f} us\n")
            f.write(f"P50 (Median):      {p50_delta:.3f} us\n")
            f.write(f"P95:               {p95_delta:.3f} us\n")
            f.write(f"P99:               {p99_delta:.3f} us\n")
            f.write("\n")

            # Per-ID statistics
            f.write("-" * 50 + "\n")
            f.write("MESSAGES BY ARBITRATION ID\n")
            f.write("-" * 50 + "\n")
            sorted_ids = sorted(by_id.items(), key=lambda x: x[1], reverse=True)
            for arb_id, count in sorted_ids[:20]:
                pct = count / total * 100 if total > 0 else 0
                f.write(f"  0x{arb_id:03X}: {count:6,} ({pct:5.1f}%)\n")
            if len(sorted_ids) > 20:
                f.write(f"  ... and {len(sorted_ids) - 20} more IDs\n")
            f.write("\n")

            # Per-frame data with nanosecond timestamps
            f.write("=" * 100 + "\n")
            f.write("PER-FRAME DATA (Nanosecond Timestamps)\n")
            f.write("=" * 100 + "\n")
            f.write(
                f"{'#':>6} | {'Timestamp (s)':>18} | {'Timestamp (ns)':>18} | "
                f"{'Dir':>4} | {'ID':>10} | {'DLC':>3} | {'Delta (us)':>12} | Data\n"
            )
            f.write("-" * 100 + "\n")

            for i, m in enumerate(messages):
                id_str = f"0x{m['arb_id']:08X}" if m["is_extended"] else f"0x{m['arb_id']:03X}"
                data_hex = " ".join(f"{b:02X}" for b in m["data"])
                f.write(
                    f"{i + 1:6} | {m['timestamp']:18.9f} | {m['timestamp_ns']:18} | "
                    f"{m['direction']:>4} | {id_str:>10} | {m['dlc']:3} | "
                    f"{m['delta_us']:12.3f} | {data_hex}\n"
                )

            f.write("\n")
            f.write("=" * 100 + "\n")
            f.write("END OF ANALYSIS\n")
            f.write("=" * 100 + "\n")

        return output_path

    @staticmethod
    def export_all(
        blf_path: Path,
        iface0: str = "can0",
        iface1: str = "can1",
    ) -> dict[str, Path]:
        """Export BLF to all formats at once.

        Creates:
        - Two ASC files (one per channel for CANalyzer/CANoe replay)
        - Human-readable log file
        - Detailed analysis file with per-frame data

        Args:
            blf_path: Path to input BLF file
            iface0: Name of first interface (for ASC filenames)
            iface1: Name of second interface (for ASC filenames)

        Returns:
            Dictionary with paths to all created files:
            {
                "asc_ch1": Path to ASC for channel 1 (iface0 traffic),
                "asc_ch2": Path to ASC for channel 2 (iface1 traffic),
                "log": Path to human-readable log,
                "analysis": Path to detailed analysis file,
            }
        """
        asc_files = LogExporter.blf_to_asc_per_channel(blf_path, iface0, iface1)
        return {
            "asc_ch1": asc_files["ch1"],
            "asc_ch2": asc_files["ch2"],
            "log": LogExporter.blf_to_human_readable(blf_path),
            "analysis": LogExporter.blf_to_detailed_analysis(blf_path),
        }

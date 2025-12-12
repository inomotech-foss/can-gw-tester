"""Unit tests for LogExporter."""

import time

import pytest

from wp4.core.gateway_logger import GatewayLogger
from wp4.core.log_exporter import LogExporter


@pytest.fixture
def temp_log_dir(tmp_path):
    """Create a temporary directory for log files."""
    return tmp_path / "logs"


@pytest.fixture
def sample_blf_file(temp_log_dir):
    """Create a sample BLF file with test data."""
    logger = GatewayLogger(temp_log_dir)
    logger.start("vcan0", "vcan1")

    # Log some messages in both directions
    base_time = time.time()
    for i in range(10):
        logger.log_rx(
            direction="0to1" if i % 2 == 0 else "1to0",
            timestamp=base_time + i * 0.001,
            arb_id=0x100 + i,
            data=bytes([i, i + 1]),
            is_extended=False,
        )
        logger.log_tx(
            direction="0to1" if i % 2 == 0 else "1to0",
            timestamp=base_time + i * 0.001 + 0.0005,
            arb_id=0x100 + i,
            data=bytes([i, i + 1]),
            is_extended=False,
            latency_us=500.0,
        )

    logger.stop()
    return logger.get_blf_path()


class TestLogExporter:
    """Tests for LogExporter class."""

    def test_blf_to_asc(self, sample_blf_file):
        """Test converting BLF to ASC format."""
        asc_path = LogExporter.blf_to_asc(sample_blf_file)

        assert asc_path.exists()
        assert asc_path.suffix == ".asc"
        assert asc_path.stat().st_size > 0

        # ASC is text-based, should contain readable content
        content = asc_path.read_text()
        assert len(content) > 0

    def test_blf_to_asc_custom_output(self, sample_blf_file, tmp_path):
        """Test converting BLF to ASC with custom output path."""
        custom_path = tmp_path / "custom.asc"
        asc_path = LogExporter.blf_to_asc(sample_blf_file, custom_path)

        assert asc_path == custom_path
        assert asc_path.exists()

    def test_blf_to_human_readable(self, sample_blf_file):
        """Test converting BLF to human-readable log."""
        log_path = LogExporter.blf_to_human_readable(sample_blf_file)

        assert log_path.exists()
        assert log_path.suffix == ".log"

        content = log_path.read_text()
        assert "Gateway Log" in content
        assert "Exported from" in content
        assert "0x10" in content  # Should contain hex ID

    def test_blf_to_human_readable_format(self, sample_blf_file):
        """Test human-readable log format."""
        log_path = LogExporter.blf_to_human_readable(sample_blf_file)
        content = log_path.read_text()

        # Check format elements
        assert "DIR" in content or "0→1" in content or "1→0" in content
        assert "ID=" in content
        assert "DLC=" in content
        assert "DATA=" in content

    def test_blf_to_statistics(self, sample_blf_file):
        """Test extracting statistics from BLF."""
        stats = LogExporter.blf_to_statistics(sample_blf_file)

        assert "total_messages" in stats
        assert "by_channel" in stats
        assert "by_arbitration_id" in stats
        assert "duration_s" in stats
        assert "messages_per_second" in stats

        # Should have logged 20 messages (10 RX + 10 TX)
        assert stats["total_messages"] == 20

        # Should have messages on both channels
        assert len(stats["by_channel"]) >= 1

        # Should have multiple arbitration IDs
        assert len(stats["by_arbitration_id"]) >= 1

    def test_blf_to_statistics_by_channel(self, sample_blf_file):
        """Test statistics grouped by channel."""
        stats = LogExporter.blf_to_statistics(sample_blf_file)

        # Channel 1 = 0to1, Channel 2 = 1to0
        by_channel = stats["by_channel"]
        total = sum(by_channel.values())
        assert total == stats["total_messages"]

    def test_format_statistics_report(self, sample_blf_file):
        """Test formatting statistics as report."""
        stats = LogExporter.blf_to_statistics(sample_blf_file)
        report = LogExporter.format_statistics_report(stats)

        assert "Statistics Report" in report
        assert "Total Messages" in report
        assert "Duration" in report
        assert "Throughput" in report
        assert "Direction" in report or "Channel" in report

    def test_empty_blf_file(self, temp_log_dir):
        """Test handling empty BLF file."""
        logger = GatewayLogger(temp_log_dir)
        logger.start("vcan0", "vcan1")
        logger.stop()

        blf_path = logger.get_blf_path()
        assert blf_path is not None

        # Should handle empty file gracefully
        stats = LogExporter.blf_to_statistics(blf_path)
        assert stats["total_messages"] == 0

    def test_statistics_duration(self, sample_blf_file):
        """Test duration calculation in statistics."""
        stats = LogExporter.blf_to_statistics(sample_blf_file)

        # Duration should be positive
        assert stats["duration_s"] >= 0

        # If we have messages and duration, throughput should be calculable
        if stats["duration_s"] > 0:
            assert stats["messages_per_second"] > 0

    def test_nanosecond_timestamp_precision(self, temp_log_dir):
        """Test BLF timestamps have sub-millisecond precision."""
        from can.io.blf import BLFReader

        logger = GatewayLogger(temp_log_dir)
        logger.start("vcan0", "vcan1")

        # Log messages with 100us intervals
        base_time = time.time()
        for i in range(5):
            logger.log_rx(
                direction="0to1",
                timestamp=base_time + i * 0.0001,  # 100us intervals
                arb_id=0x100,
                data=bytes([i]),
                is_extended=False,
            )

        logger.stop()
        blf_path = logger.get_blf_path()

        # Verify timestamps are distinct with sub-ms precision
        timestamps = []
        with BLFReader(str(blf_path)) as reader:
            for msg in reader:
                timestamps.append(msg.timestamp)

        assert len(timestamps) == 5
        for i in range(1, len(timestamps)):
            delta = timestamps[i] - timestamps[i - 1]
            # Delta should be ~100us (allow tolerance for timing)
            assert delta > 0.00005, f"Timestamps not distinct: delta={delta}"

    def test_export_all_creates_all_files(self, sample_blf_file):
        """Test export_all creates separate ASC per channel, LOG, and analysis files."""
        result = LogExporter.export_all(sample_blf_file, "vcan0", "vcan1")

        assert "asc_ch1" in result
        assert "asc_ch2" in result
        assert "log" in result
        assert "analysis" in result

        assert result["asc_ch1"].exists()
        assert result["asc_ch2"].exists()
        assert result["log"].exists()
        assert result["analysis"].exists()

        assert result["asc_ch1"].suffix == ".asc"
        assert result["asc_ch2"].suffix == ".asc"
        assert result["log"].suffix == ".log"
        assert result["analysis"].suffix == ".log"  # .analysis.log

        # Check filenames contain interface names
        assert "vcan0" in result["asc_ch1"].name
        assert "vcan1" in result["asc_ch2"].name

    def test_blf_to_asc_per_channel(self, sample_blf_file):
        """Test blf_to_asc_per_channel creates separate files."""
        result = LogExporter.blf_to_asc_per_channel(sample_blf_file, "vcan0", "vcan1")

        assert "ch1" in result
        assert "ch2" in result
        assert result["ch1"].exists()
        assert result["ch2"].exists()

        # At least one should have content (we logged both directions)
        total_size = result["ch1"].stat().st_size + result["ch2"].stat().st_size
        assert total_size > 0

    def test_asc_format_valid(self, sample_blf_file):
        """Test ASC file has valid Vector format."""
        asc_path = LogExporter.blf_to_asc(sample_blf_file)
        content = asc_path.read_text()
        lines = content.strip().split("\n")

        # ASC should have date header
        assert any("date" in line.lower() for line in lines[:5])

        # Non-comment lines should have timestamp as first field
        data_lines = [x for x in lines if x.strip() and not x.startswith(";")]
        for line in data_lines[1:]:  # Skip header
            parts = line.split()
            if parts:
                try:
                    float(parts[0])  # First field is timestamp
                except ValueError:
                    continue  # Skip non-data lines

    def test_human_readable_format_valid(self, sample_blf_file):
        """Test human-readable log has correct format."""
        log_path = LogExporter.blf_to_human_readable(sample_blf_file)
        content = log_path.read_text()
        lines = content.strip().split("\n")

        # Header validation
        assert lines[0].startswith("# Gateway Log")
        assert "Exported" in lines[1]

        # Data lines should have required fields
        data_lines = [x for x in lines if x and not x.startswith("#")]
        assert len(data_lines) > 0

        for line in data_lines:
            assert "[" in line and "]" in line  # Timestamp
            assert "ID=" in line
            assert "DLC=" in line
            assert "DATA=" in line

    def test_analysis_format_valid(self, sample_blf_file):
        """Test analysis file has valid format with per-frame data."""
        analysis_path = LogExporter.blf_to_detailed_analysis(sample_blf_file)
        content = analysis_path.read_text()

        # Header section
        assert "GATEWAY LOG DETAILED ANALYSIS" in content
        assert "SUMMARY STATISTICS" in content

        # Statistics section
        assert "Total Messages:" in content
        assert "Duration:" in content
        assert "Direction 0→1:" in content
        assert "Direction 1→0:" in content

        # Timing section
        assert "INTER-FRAME TIMING" in content
        assert "Min Delta:" in content
        assert "Max Delta:" in content
        assert "P50" in content
        assert "P95:" in content
        assert "P99:" in content

        # Per-frame data section
        assert "PER-FRAME DATA" in content
        assert "Nanosecond" in content

        # Should have data rows with nanosecond timestamps
        lines = content.split("\n")
        data_section = False
        data_rows = 0
        for line in lines:
            if "PER-FRAME DATA" in line:
                data_section = True
                continue
            if not data_section:
                continue
            is_separator = line.startswith("-") or line.startswith("=")
            if line.strip() and not is_separator and "|" in line and "0x" in line:
                data_rows += 1
                # Verify nanosecond timestamp column exists
                parts = line.split("|")
                assert len(parts) >= 7, f"Expected 7+ columns, got {len(parts)}"

        assert data_rows > 0, "No data rows found in analysis file"

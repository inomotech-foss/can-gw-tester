"""Unit tests for BLF-based GatewayLogger."""

import time

import pytest

from wp4.core.gateway_logger import GatewayLogger


@pytest.fixture
def temp_log_dir(tmp_path):
    """Create a temporary directory for log files."""
    return tmp_path / "logs"


class TestGatewayLogger:
    """Tests for GatewayLogger with BLF format."""

    def test_init_disabled(self):
        """Test GatewayLogger is disabled when no path provided."""
        logger = GatewayLogger()
        assert not logger.is_enabled

    def test_init_with_path(self, temp_log_dir):
        """Test GatewayLogger with path."""
        logger = GatewayLogger(temp_log_dir)
        assert not logger.is_enabled  # Not started yet

    def test_start_creates_blf_file(self, temp_log_dir):
        """Test start() creates BLF log file."""
        logger = GatewayLogger(temp_log_dir)
        logger.start("vcan0", "vcan1")

        assert logger.is_enabled
        blf_path = logger.get_blf_path()
        assert blf_path is not None
        assert blf_path.exists()
        assert blf_path.suffix == ".blf"
        assert "vcan0" in blf_path.name
        assert "vcan1" in blf_path.name

        logger.stop()

    def test_start_creates_parent_directories(self, temp_log_dir):
        """Test start() creates parent directories if needed."""
        nested_path = temp_log_dir / "nested" / "dirs"
        logger = GatewayLogger(nested_path)
        logger.start("vcan0", "vcan1")

        assert nested_path.exists()
        blf_path = logger.get_blf_path()
        assert blf_path is not None
        assert blf_path.exists()

        logger.stop()

    def test_start_without_path_does_nothing(self):
        """Test start() does nothing when path is not set."""
        logger = GatewayLogger()
        logger.start("vcan0", "vcan1")
        assert not logger.is_enabled

    def test_stop_cleans_up(self, temp_log_dir):
        """Test stop() cleans up resources."""
        logger = GatewayLogger(temp_log_dir)
        logger.start("vcan0", "vcan1")
        logger.stop()

        assert not logger.is_enabled

    def test_log_rx_writes_to_blf(self, temp_log_dir):
        """Test log_rx writes message to BLF file."""
        logger = GatewayLogger(temp_log_dir)
        logger.start("vcan0", "vcan1")

        logger.log_rx(
            direction="0to1",
            timestamp=time.time(),
            arb_id=0x123,
            data=bytes([0x01, 0x02]),
            is_extended=False,
        )

        logger.stop()

        # Verify BLF file was created and has data
        blf_path = logger.get_blf_path()
        assert blf_path is not None
        assert blf_path.exists()
        assert blf_path.stat().st_size > 0

    def test_log_tx_writes_to_blf(self, temp_log_dir):
        """Test log_tx writes message to BLF file."""
        logger = GatewayLogger(temp_log_dir)
        logger.start("vcan0", "vcan1")

        logger.log_tx(
            direction="0to1",
            timestamp=time.time(),
            arb_id=0x456,
            data=bytes([0xAA, 0xBB]),
            is_extended=False,
            latency_us=1000.0,
        )

        logger.stop()

        blf_path = logger.get_blf_path()
        assert blf_path is not None
        assert blf_path.exists()
        assert blf_path.stat().st_size > 0

    def test_log_queue_is_noop(self, temp_log_dir):
        """Test log_queue is a no-op (delay visible from RX/TX timing)."""
        logger = GatewayLogger(temp_log_dir)
        logger.start("vcan0", "vcan1")

        # Should not raise
        logger.log_queue(
            direction="0to1",
            timestamp=time.time(),
            arb_id=0x123,
            data=bytes([0x01]),
            is_extended=False,
            scheduled_time=time.time() + 0.1,
        )

        logger.stop()

    def test_log_drop_writes_csv(self, temp_log_dir):
        """Test log_drop writes to CSV (not to BLF)."""
        logger = GatewayLogger(temp_log_dir)
        logger.start("vcan0", "vcan1")

        logger.log_drop(
            direction="1to0",
            timestamp=time.time(),
            arb_id=0xABC,
            data=bytes([0xFF]),
            is_extended=False,
        )

        logger.stop()

        # CSV should exist and have the dropped event
        csv_path = logger.get_csv_path()
        assert csv_path is not None
        assert csv_path.exists()

        import csv

        with csv_path.open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]["event"] == "dropped"
        assert rows[0]["direction"] == "1to0"
        assert rows[0]["tx_ts"] == ""  # No TX timestamp for dropped
        assert rows[0]["latency_us"] == ""  # No latency for dropped

    def test_log_when_disabled(self):
        """Test logging does nothing when disabled."""
        logger = GatewayLogger()

        # Should not raise
        logger.log_rx("0to1", time.time(), 0x123, bytes([0x01]), False)
        logger.log_queue("0to1", time.time(), 0x123, bytes([0x01]), False, time.time())
        logger.log_tx("0to1", time.time(), 0x123, bytes([0x01]), False, 1000.0)
        logger.log_drop("0to1", time.time(), 0x123, bytes([0x01]), False)

    def test_set_log_path(self, temp_log_dir):
        """Test set_log_path changes the base path."""
        logger = GatewayLogger()
        logger.set_log_path(temp_log_dir)
        logger.start("vcan0", "vcan1")

        assert logger.is_enabled
        logger.stop()

    def test_set_log_path_none_disables(self, temp_log_dir):
        """Test set_log_path(None) disables logging."""
        logger = GatewayLogger(temp_log_dir)
        logger.set_log_path(None)
        logger.start("vcan0", "vcan1")

        assert not logger.is_enabled

    def test_get_log_paths_returns_blf_path(self, temp_log_dir):
        """Test get_log_paths returns BLF path for both directions."""
        logger = GatewayLogger(temp_log_dir)
        logger.start("vcan0", "vcan1")

        paths = logger.get_log_paths()
        assert paths["0to1"] is not None
        assert paths["1to0"] is not None
        # Both should point to the same BLF file
        assert paths["0to1"] == paths["1to0"]
        assert paths["0to1"].suffix == ".blf"

        logger.stop()

    def test_channel_mapping(self, temp_log_dir):
        """Test direction is encoded in channel field."""
        logger = GatewayLogger(temp_log_dir)

        # Verify channel mapping
        assert logger.CHANNEL_MAP["0to1"] == 1
        assert logger.CHANNEL_MAP["1to0"] == 2

    def test_multiple_messages(self, temp_log_dir):
        """Test logging multiple messages."""
        logger = GatewayLogger(temp_log_dir)
        logger.start("vcan0", "vcan1")

        # Log multiple messages in both directions
        for i in range(10):
            logger.log_rx(
                direction="0to1" if i % 2 == 0 else "1to0",
                timestamp=time.time(),
                arb_id=0x100 + i,
                data=bytes([i]),
                is_extended=False,
            )

        logger.stop()

        blf_path = logger.get_blf_path()
        assert blf_path is not None
        assert blf_path.exists()
        # File should have meaningful size after multiple messages
        assert blf_path.stat().st_size > 100

    def test_extended_id(self, temp_log_dir):
        """Test logging message with extended CAN ID."""
        logger = GatewayLogger(temp_log_dir)
        logger.start("vcan0", "vcan1")

        logger.log_rx(
            direction="0to1",
            timestamp=time.time(),
            arb_id=0x18DAF100,
            data=bytes([0x01, 0x02]),
            is_extended=True,
        )

        logger.stop()

        blf_path = logger.get_blf_path()
        assert blf_path is not None
        assert blf_path.exists()


class TestCSVLogging:
    """Tests for CSV logging functionality."""

    def test_csv_file_created(self, temp_log_dir):
        """Test CSV file is created alongside BLF."""
        logger = GatewayLogger(temp_log_dir)
        logger.start("vcan0", "vcan1")

        blf_path = logger.get_blf_path()
        csv_path = logger.get_csv_path()

        assert blf_path is not None
        assert csv_path is not None
        assert blf_path.exists()
        assert csv_path.exists()
        assert csv_path.suffix == ".csv"
        # Same base name, different extension
        assert blf_path.stem == csv_path.stem

        logger.stop()

    def test_csv_header(self, temp_log_dir):
        """Test CSV header contains all 12 columns."""
        import csv

        logger = GatewayLogger(temp_log_dir)
        logger.start("vcan0", "vcan1")
        logger.stop()

        csv_path = logger.get_csv_path()
        assert csv_path is not None

        with csv_path.open() as f:
            reader = csv.reader(f)
            header = next(reader)

        expected_columns = [
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
        assert header == expected_columns

    def test_log_tx_writes_csv(self, temp_log_dir):
        """Test log_tx writes to CSV with correct values."""
        import csv

        logger = GatewayLogger(temp_log_dir)
        logger.set_gateway_config(delay_ms=50.0, jitter_ms=10.0, loss_pct=5.0)
        logger.start("vcan0", "vcan1")

        tx_timestamp = time.time()
        logger.log_tx(
            direction="0to1",
            timestamp=tx_timestamp,
            arb_id=0x123,
            data=bytes([0xAA, 0xBB, 0xCC]),
            is_extended=False,
            latency_us=52345.6,
        )

        logger.stop()

        csv_path = logger.get_csv_path()
        assert csv_path is not None
        with csv_path.open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        row = rows[0]
        assert row["seq"] == "1"
        assert row["event"] == "forwarded"
        assert row["direction"] == "0to1"
        assert row["rx_ts"] != ""  # RX timestamp should be set
        assert row["tx_ts"] != ""  # TX timestamp should be set
        assert row["arb_id"] == "0x123"
        assert row["dlc"] == "3"
        assert row["data"] == "AA BB CC"
        assert row["delay_ms"] == "50.0"
        assert row["jitter_ms"] == "10.0"
        assert row["loss_pct"] == "5.0"
        assert row["latency_us"] == "52345.6"

    def test_set_gateway_config(self, temp_log_dir):
        """Test set_gateway_config values appear in CSV rows."""
        import csv

        logger = GatewayLogger(temp_log_dir)
        logger.set_gateway_config(delay_ms=100.0, jitter_ms=25.0, loss_pct=10.0)
        logger.start("vcan0", "vcan1")

        logger.log_tx(
            direction="0to1",
            timestamp=time.time(),
            arb_id=0x100,
            data=bytes([0x01]),
            is_extended=False,
            latency_us=1000.0,
        )

        logger.stop()

        csv_path = logger.get_csv_path()
        assert csv_path is not None
        with csv_path.open() as f:
            reader = csv.DictReader(f)
            row = next(reader)

        assert row["delay_ms"] == "100.0"
        assert row["jitter_ms"] == "25.0"
        assert row["loss_pct"] == "10.0"

    def test_config_updates_during_logging(self, temp_log_dir):
        """Test config changes are reflected in subsequent CSV rows."""
        import csv

        logger = GatewayLogger(temp_log_dir)
        logger.set_gateway_config(delay_ms=10.0, jitter_ms=0.0, loss_pct=0.0)
        logger.start("vcan0", "vcan1")

        # First message with initial config
        logger.log_tx(
            direction="0to1",
            timestamp=time.time(),
            arb_id=0x100,
            data=bytes([0x01]),
            is_extended=False,
            latency_us=1000.0,
        )

        # Update config
        logger.set_gateway_config(delay_ms=200.0, jitter_ms=50.0, loss_pct=20.0)

        # Second message with updated config
        logger.log_tx(
            direction="0to1",
            timestamp=time.time(),
            arb_id=0x101,
            data=bytes([0x02]),
            is_extended=False,
            latency_us=2000.0,
        )

        logger.stop()

        csv_path = logger.get_csv_path()
        assert csv_path is not None
        with csv_path.open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        # First row: initial config
        assert rows[0]["delay_ms"] == "10.0"
        assert rows[0]["jitter_ms"] == "0.0"
        assert rows[0]["loss_pct"] == "0.0"
        # Second row: updated config
        assert rows[1]["delay_ms"] == "200.0"
        assert rows[1]["jitter_ms"] == "50.0"
        assert rows[1]["loss_pct"] == "20.0"

    def test_get_csv_path(self, temp_log_dir):
        """Test get_csv_path returns correct path."""
        logger = GatewayLogger(temp_log_dir)

        # Before start, path is None
        assert logger.get_csv_path() is None

        logger.start("vcan0", "vcan1")
        csv_path = logger.get_csv_path()

        assert csv_path is not None
        assert csv_path.parent == temp_log_dir
        assert "vcan0" in csv_path.name
        assert "vcan1" in csv_path.name
        assert csv_path.suffix == ".csv"

        logger.stop()

    def test_stop_closes_csv(self, temp_log_dir):
        """Test CSV file is properly closed after stop."""
        import csv

        logger = GatewayLogger(temp_log_dir)
        logger.start("vcan0", "vcan1")

        logger.log_tx(
            direction="0to1",
            timestamp=time.time(),
            arb_id=0x123,
            data=bytes([0x01]),
            is_extended=False,
            latency_us=1000.0,
        )

        csv_path = logger.get_csv_path()
        assert csv_path is not None
        logger.stop()

        # File should be readable after stop
        with csv_path.open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1

    def test_get_log_paths_includes_csv(self, temp_log_dir):
        """Test get_log_paths returns both BLF and CSV paths."""
        logger = GatewayLogger(temp_log_dir)
        logger.start("vcan0", "vcan1")

        paths = logger.get_log_paths()

        assert "blf" in paths
        assert "csv" in paths
        assert paths["blf"] is not None
        assert paths["csv"] is not None
        assert paths["blf"].suffix == ".blf"
        assert paths["csv"].suffix == ".csv"

        logger.stop()

    def test_sequence_numbers(self, temp_log_dir):
        """Test sequence numbers increment correctly."""
        import csv

        logger = GatewayLogger(temp_log_dir)
        logger.start("vcan0", "vcan1")

        for i in range(5):
            logger.log_tx(
                direction="0to1",
                timestamp=time.time(),
                arb_id=0x100 + i,
                data=bytes([i]),
                is_extended=False,
                latency_us=1000.0,
            )

        logger.stop()

        csv_path = logger.get_csv_path()
        assert csv_path is not None
        with csv_path.open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 5
        for i, row in enumerate(rows, start=1):
            assert row["seq"] == str(i)

    def test_extended_id_format(self, temp_log_dir):
        """Test extended CAN ID is formatted with 8 hex digits."""
        import csv

        logger = GatewayLogger(temp_log_dir)
        logger.start("vcan0", "vcan1")

        # Extended ID
        logger.log_tx(
            direction="0to1",
            timestamp=time.time(),
            arb_id=0x18DAF100,
            data=bytes([0x01]),
            is_extended=True,
            latency_us=1000.0,
        )

        # Standard ID
        logger.log_tx(
            direction="0to1",
            timestamp=time.time(),
            arb_id=0x123,
            data=bytes([0x02]),
            is_extended=False,
            latency_us=1000.0,
        )

        logger.stop()

        csv_path = logger.get_csv_path()
        assert csv_path is not None
        with csv_path.open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Extended: 8 hex digits
        assert rows[0]["arb_id"] == "0x18DAF100"
        # Standard: 3 hex digits
        assert rows[1]["arb_id"] == "0x123"

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

    def test_log_drop_is_noop(self, temp_log_dir):
        """Test log_drop is a no-op (drops are implicit from missing TX)."""
        logger = GatewayLogger(temp_log_dir)
        logger.start("vcan0", "vcan1")

        # Should not raise
        logger.log_drop(
            direction="1to0",
            timestamp=time.time(),
            arb_id=0xABC,
            data=bytes([0xFF]),
            is_extended=False,
        )

        logger.stop()

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

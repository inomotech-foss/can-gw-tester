"""Tests for latency measurement logic."""

import threading
import time

import pytest


class MockLatencyListener:
    """Simplified version of _PassiveLatencyListener for testing."""

    def __init__(self, iface0: str, iface1: str):
        self._iface0 = iface0
        self._iface1 = iface1
        self._pending: dict[int, tuple[int, str]] = {}
        self._lock = threading.Lock()
        self._results: list[tuple[str, float]] = []

    def receive_on(self, iface: str, arb_id: int, data: bytes, timestamp_ns: int):
        """Simulate receiving a message on an interface."""
        msg_hash = hash((arb_id, bytes(data)))

        with self._lock:
            if msg_hash in self._pending:
                start_ns, src_iface = self._pending[msg_hash]
                if src_iface != iface:
                    latency_us = (timestamp_ns - start_ns) / 1000
                    direction = "0to1" if src_iface == self._iface0 else "1to0"
                    self._results.append((direction, latency_us))
                    del self._pending[msg_hash]
            else:
                self._pending[msg_hash] = (timestamp_ns, iface)


class TestLatencyMeasurement:
    """Tests for latency measurement logic."""

    def test_basic_latency_measurement(self):
        """Test basic latency measurement between interfaces."""
        listener = MockLatencyListener("can0", "can1")

        # Message first seen on can1 at T=0
        t0 = 0
        listener.receive_on("can1", 0x123, b"\x01\x02", t0)

        # Same message seen on can0 at T=500ms (500000000 ns)
        t1 = 500_000_000  # 500ms in nanoseconds
        listener.receive_on("can0", 0x123, b"\x01\x02", t1)

        # Should have one latency result
        assert len(listener._results) == 1
        direction, latency_us = listener._results[0]
        assert direction == "1to0"  # can1 -> can0
        assert latency_us == 500_000  # 500ms in microseconds

    def test_reverse_direction(self):
        """Test latency in opposite direction."""
        listener = MockLatencyListener("can0", "can1")

        # Message first seen on can0
        t0 = 0
        listener.receive_on("can0", 0x456, b"\xaa", t0)

        # Same message seen on can1 after 100ms
        t1 = 100_000_000  # 100ms
        listener.receive_on("can1", 0x456, b"\xaa", t1)

        assert len(listener._results) == 1
        direction, latency_us = listener._results[0]
        assert direction == "0to1"  # can0 -> can1
        assert latency_us == 100_000  # 100ms

    def test_no_match_different_data(self):
        """Different data should not match."""
        listener = MockLatencyListener("can0", "can1")

        listener.receive_on("can1", 0x123, b"\x01", 0)
        listener.receive_on("can0", 0x123, b"\x02", 100_000_000)  # Different data

        # No match because data is different
        assert len(listener._results) == 0
        # Both should be pending
        assert len(listener._pending) == 2

    def test_no_match_different_id(self):
        """Different ID should not match."""
        listener = MockLatencyListener("can0", "can1")

        listener.receive_on("can1", 0x123, b"\x01", 0)
        listener.receive_on("can0", 0x124, b"\x01", 100_000_000)  # Different ID

        assert len(listener._results) == 0
        assert len(listener._pending) == 2

    def test_same_interface_no_latency(self):
        """Message seen twice on same interface should not measure latency."""
        listener = MockLatencyListener("can0", "can1")

        listener.receive_on("can1", 0x123, b"\x01", 0)
        listener.receive_on("can1", 0x123, b"\x01", 100_000_000)  # Same interface

        # Second receive updates the pending entry but no latency measured
        assert len(listener._results) == 0

    def test_order_independence(self):
        """Latency should be measured regardless of which interface sees first."""
        listener = MockLatencyListener("can0", "can1")

        # can0 sees message first this time
        listener.receive_on("can0", 0x789, b"\xff", 0)
        listener.receive_on("can1", 0x789, b"\xff", 200_000_000)

        assert len(listener._results) == 1
        direction, latency_us = listener._results[0]
        assert direction == "0to1"
        assert latency_us == 200_000


class TestForwardingWithLatency:
    """Test that simulates the full forwarding + latency measurement flow."""

    def test_full_flow_with_delay(self):
        """Simulate: cangen -> can1 -> forwarder (delay) -> can0.

        Flow:
        1. T0: cangen sends on can1
        2. T0: Latency listener sees on can1, stores hash
        3. T0: Forwarder receives on can1, queues with delay
        4. T0+delay: Forwarder sends to can0
        5. T0+delay: Latency listener sees on can0, measures latency
        """
        listener = MockLatencyListener("vcan0", "vcan1")
        delay_ms = 500

        # Step 1-2: Message arrives on vcan1 at T0
        t0_ns = time.time_ns()
        listener.receive_on("vcan1", 0x100, b"\xde\xad\xbe\xef", t0_ns)

        # Step 4-5: After delay, message arrives on vcan0
        time.sleep(delay_ms / 1000)
        t1_ns = time.time_ns()
        listener.receive_on("vcan0", 0x100, b"\xde\xad\xbe\xef", t1_ns)

        # Verify latency measured
        assert len(listener._results) == 1
        direction, latency_us = listener._results[0]

        assert direction == "1to0"  # vcan1 -> vcan0

        # Latency should be approximately the delay (within 50ms tolerance)
        expected_us = delay_ms * 1000  # 500000 us
        assert abs(latency_us - expected_us) < 50_000, (
            f"Latency {latency_us}us not close to expected {expected_us}us"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

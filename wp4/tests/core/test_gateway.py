"""Unit and integration tests for BidirectionalGateway."""

import threading
import time

import can
import pytest

from wp4.core.gateway import BidirectionalGateway


@pytest.fixture
def gateway():
    """Create a gateway using vcan interfaces."""
    gw = BidirectionalGateway(
        iface0="vcan0",
        iface1="vcan1",
        delay_ms=0,
        loss_pct=0.0,
        jitter_ms=0.0,
    )
    yield gw
    # Cleanup
    if gw.is_running:
        gw.stop()


@pytest.fixture
def gateway_with_delay():
    """Create a gateway with delay."""
    gw = BidirectionalGateway(
        iface0="vcan0",
        iface1="vcan1",
        delay_ms=50,
        loss_pct=0.0,
        jitter_ms=0.0,
    )
    yield gw
    if gw.is_running:
        gw.stop()


class TestGatewayInit:
    """Tests for gateway initialization."""

    def test_default_values(self):
        """Test gateway initializes with correct default values."""
        gw = BidirectionalGateway("vcan0", "vcan1")
        assert gw.delay_ms == 0
        assert gw.loss_pct == 0.0
        assert gw.jitter_ms == 0.0
        assert not gw.is_running

    def test_custom_values(self):
        """Test gateway initializes with custom values."""
        gw = BidirectionalGateway(
            "vcan0",
            "vcan1",
            delay_ms=100,
            loss_pct=5.0,
            jitter_ms=10.0,
        )
        assert gw.delay_ms == 100
        assert gw.loss_pct == 5.0
        assert gw.jitter_ms == 10.0

    def test_negative_jitter_clamped(self):
        """Test negative jitter is clamped to zero."""
        gw = BidirectionalGateway("vcan0", "vcan1", jitter_ms=-10.0)
        assert gw.jitter_ms == 0.0


class TestGatewayLifecycle:
    """Tests for gateway start/stop lifecycle."""

    def test_start_sets_running(self, gateway):
        """Test start() sets is_running to True."""
        assert not gateway.is_running
        gateway.start()
        assert gateway.is_running

    def test_stop_clears_running(self, gateway):
        """Test stop() sets is_running to False."""
        gateway.start()
        gateway.stop()
        assert not gateway.is_running

    def test_start_resets_stats(self, gateway):
        """Test start() resets statistics."""
        gateway.start()
        # Stats should be zero after start
        assert gateway.received_0to1 == 0
        assert gateway.forwarded_0to1 == 0
        assert gateway.dropped_0to1 == 0
        assert gateway.received_1to0 == 0
        assert gateway.forwarded_1to0 == 0
        assert gateway.dropped_1to0 == 0

    def test_start_idempotent(self, gateway):
        """Test starting an already running gateway does nothing."""
        gateway.start()
        # Start again should not fail
        gateway.start()
        assert gateway.is_running

    def test_stop_when_not_running(self, gateway):
        """Test stop() when not running doesn't raise exception."""
        gateway.stop()  # Should not raise

    def test_multiple_start_stop_cycles(self, gateway):
        """Test multiple start/stop cycles work correctly."""
        for _ in range(3):
            gateway.start()
            assert gateway.is_running
            gateway.stop()
            assert not gateway.is_running


class TestGatewayProperties:
    """Tests for gateway property setters."""

    def test_delay_setter(self, gateway):
        """Test delay_ms setter."""
        gateway.delay_ms = 100
        assert gateway.delay_ms == 100

    def test_loss_pct_setter(self, gateway):
        """Test loss_pct setter."""
        gateway.loss_pct = 10.0
        assert gateway.loss_pct == 10.0

    def test_jitter_setter(self, gateway):
        """Test jitter_ms setter clamps negative values."""
        gateway.jitter_ms = 20.0
        assert gateway.jitter_ms == 20.0

        gateway.jitter_ms = -5.0
        assert gateway.jitter_ms == 0.0

    def test_properties_while_running(self, gateway):
        """Test properties can be changed while running."""
        gateway.start()
        gateway.delay_ms = 50
        gateway.loss_pct = 5.0
        gateway.jitter_ms = 10.0

        assert gateway.delay_ms == 50
        assert gateway.loss_pct == 5.0
        assert gateway.jitter_ms == 10.0


class TestDirectionControl:
    """Tests for direction enable/disable."""

    def test_set_direction_0to1(self, gateway):
        """Test disabling 0to1 direction."""
        gateway.start()
        gateway.set_direction_enabled("0to1", False)
        # Direction should be disabled (verified by behavior in forwarding test)
        gateway.set_direction_enabled("0to1", True)

    def test_set_direction_1to0(self, gateway):
        """Test disabling 1to0 direction."""
        gateway.start()
        gateway.set_direction_enabled("1to0", False)
        gateway.set_direction_enabled("1to0", True)


class TestLatencySamples:
    """Tests for latency sample management."""

    def test_get_latency_samples_empty(self, gateway):
        """Test getting latency samples when empty."""
        gateway.start()
        samples = gateway.get_latency_samples("0to1")
        assert isinstance(samples, list)

    def test_clear_latency_samples(self, gateway):
        """Test clearing latency samples."""
        gateway.start()
        gateway.clear_latency_samples()
        assert gateway.get_latency_samples("0to1") == []
        assert gateway.get_latency_samples("1to0") == []

    def test_latency_samples_max_size(self, gateway):
        """Test latency samples are capped at max size."""
        # The deque has maxlen=100 (defined in DirectionStats)
        gateway.start()
        # After forwarding many messages, samples should be <= max
        time.sleep(0.1)
        samples = gateway.get_latency_samples("0to1")
        # Max is 100 as defined in DirectionStats.latency_samples deque
        assert len(samples) <= 100


class TestStatistics:
    """Tests for statistics counters."""

    def test_stats_thread_safe(self, gateway):
        """Test statistics access is thread-safe."""
        gateway.start()
        # Accessing stats from multiple threads should not raise
        results = []

        def read_stats():
            for _ in range(100):
                results.append(gateway.received_0to1)
                results.append(gateway.forwarded_0to1)
                results.append(gateway.dropped_0to1)

        threads = [threading.Thread(target=read_stats) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All values should be valid integers
        assert all(isinstance(r, int) for r in results)

    def test_queue_size_properties(self, gateway):
        """Test queue size properties."""
        gateway.start()
        assert gateway.queue_size_0to1 >= 0
        assert gateway.queue_size_1to0 >= 0


class TestMessageForwarding:
    """Integration tests for actual message forwarding."""

    def test_forward_0to1(self, gateway):
        """Test message forwarding from vcan0 to vcan1."""
        gateway.start()
        time.sleep(0.1)  # Let gateway initialize

        # Create send and receive buses
        with (
            can.Bus(channel="vcan0", interface="socketcan") as send_bus,
            can.Bus(channel="vcan1", interface="socketcan") as recv_bus,
        ):
            # Send a message on vcan0
            test_msg = can.Message(
                arbitration_id=0x123,
                data=bytes([0x11, 0x22, 0x33, 0x44]),
                is_extended_id=False,
            )
            send_bus.send(test_msg)

            # Receive on vcan1
            recv_msg = recv_bus.recv(timeout=1.0)

            assert recv_msg is not None
            assert recv_msg.arbitration_id == 0x123
            assert bytes(recv_msg.data) == bytes([0x11, 0x22, 0x33, 0x44])

        # Check statistics
        time.sleep(0.1)
        assert gateway.received_0to1 >= 1
        assert gateway.forwarded_0to1 >= 1

    def test_forward_1to0(self, gateway):
        """Test message forwarding from vcan1 to vcan0."""
        gateway.start()
        time.sleep(0.1)

        with (
            can.Bus(channel="vcan1", interface="socketcan") as send_bus,
            can.Bus(channel="vcan0", interface="socketcan") as recv_bus,
        ):
            test_msg = can.Message(
                arbitration_id=0x456,
                data=bytes([0xAA, 0xBB]),
                is_extended_id=False,
            )
            send_bus.send(test_msg)

            recv_msg = recv_bus.recv(timeout=1.0)

            assert recv_msg is not None
            assert recv_msg.arbitration_id == 0x456
            assert bytes(recv_msg.data) == bytes([0xAA, 0xBB])

        time.sleep(0.1)
        assert gateway.received_1to0 >= 1
        assert gateway.forwarded_1to0 >= 1

    def test_forward_extended_id(self, gateway):
        """Test forwarding message with extended CAN ID."""
        gateway.start()
        time.sleep(0.1)

        with (
            can.Bus(channel="vcan0", interface="socketcan") as send_bus,
            can.Bus(channel="vcan1", interface="socketcan") as recv_bus,
        ):
            test_msg = can.Message(
                arbitration_id=0x18DAF100,
                data=bytes([0x01, 0x02]),
                is_extended_id=True,
            )
            send_bus.send(test_msg)

            recv_msg = recv_bus.recv(timeout=1.0)

            assert recv_msg is not None
            assert recv_msg.arbitration_id == 0x18DAF100
            assert recv_msg.is_extended_id is True

    def test_direction_disabled_no_forward(self, gateway):
        """Test messages are not forwarded when direction is disabled."""
        gateway.set_direction_enabled("0to1", False)
        gateway.start()
        time.sleep(0.1)

        with (
            can.Bus(channel="vcan0", interface="socketcan") as send_bus,
            can.Bus(channel="vcan1", interface="socketcan") as recv_bus,
        ):
            test_msg = can.Message(
                arbitration_id=0x789,
                data=bytes([0xFF]),
                is_extended_id=False,
            )
            send_bus.send(test_msg)

            # Should NOT receive (direction disabled)
            recv_msg = recv_bus.recv(timeout=0.3)
            assert recv_msg is None

    def test_bidirectional_forwarding(self, gateway):
        """Test simultaneous bidirectional forwarding."""
        gateway.start()
        time.sleep(0.1)

        # Send from both directions concurrently
        with (
            can.Bus(channel="vcan0", interface="socketcan") as bus0,
            can.Bus(channel="vcan1", interface="socketcan") as bus1,
        ):
            msg_0to1 = can.Message(arbitration_id=0x100, data=bytes([0x01]))
            msg_1to0 = can.Message(arbitration_id=0x200, data=bytes([0x02]))

            bus0.send(msg_0to1)
            bus1.send(msg_1to0)

            # Receive on both sides
            recv_on_1 = bus1.recv(timeout=1.0)
            recv_on_0 = bus0.recv(timeout=1.0)

            assert recv_on_1 is not None
            assert recv_on_0 is not None


class TestDelayAndJitter:
    """Tests for delay and jitter functionality."""

    def test_delay_increases_latency(self, gateway_with_delay):
        """Test that delay_ms increases message latency."""
        gateway_with_delay.start()
        time.sleep(0.1)

        with (
            can.Bus(channel="vcan0", interface="socketcan") as send_bus,
            can.Bus(channel="vcan1", interface="socketcan") as recv_bus,
        ):
            start = time.time()
            test_msg = can.Message(arbitration_id=0x111, data=bytes([0x00]))
            send_bus.send(test_msg)

            recv_msg = recv_bus.recv(timeout=1.0)
            elapsed = time.time() - start

            assert recv_msg is not None
            # Should take at least ~50ms (delay_ms=50)
            assert elapsed >= 0.04  # Allow some tolerance

        # Check latency samples were recorded
        time.sleep(0.1)
        samples = gateway_with_delay.get_latency_samples("0to1")
        assert len(samples) >= 1
        # Latency should be approximately 50000 microseconds (50ms)
        assert samples[0] >= 40000  # At least 40ms


class TestPacketLoss:
    """Tests for packet loss simulation."""

    def test_high_loss_drops_messages(self):
        """Test that high loss_pct drops messages."""
        gw = BidirectionalGateway(
            "vcan0",
            "vcan1",
            delay_ms=0,
            loss_pct=100.0,  # 100% loss
        )
        gw.start()
        time.sleep(0.1)

        try:
            with (
                can.Bus(channel="vcan0", interface="socketcan") as send_bus,
                can.Bus(channel="vcan1", interface="socketcan") as recv_bus,
            ):
                # Send multiple messages
                for i in range(5):
                    msg = can.Message(arbitration_id=0x300 + i, data=bytes([i]))
                    send_bus.send(msg)

                time.sleep(0.2)

                # Should NOT receive any (100% loss)
                recv_msg = recv_bus.recv(timeout=0.1)
                assert recv_msg is None

            # All should be dropped
            assert gw.dropped_0to1 >= 5
            assert gw.forwarded_0to1 == 0
        finally:
            gw.stop()

    def test_zero_loss_forwards_all(self, gateway):
        """Test that 0% loss forwards all messages."""
        gateway.start()
        time.sleep(0.1)

        with (
            can.Bus(channel="vcan0", interface="socketcan") as send_bus,
            can.Bus(channel="vcan1", interface="socketcan") as recv_bus,
        ):
            for i in range(5):
                msg = can.Message(arbitration_id=0x400 + i, data=bytes([i]))
                send_bus.send(msg)

            time.sleep(0.2)

            # Should receive all 5
            received = 0
            while True:
                recv_msg = recv_bus.recv(timeout=0.1)
                if recv_msg is None:
                    break
                received += 1

            assert received >= 5

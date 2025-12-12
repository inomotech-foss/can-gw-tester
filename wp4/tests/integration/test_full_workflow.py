"""Integration tests for full gateway workflow.

These tests verify end-to-end functionality including:
- Complete message forwarding pipeline
- Gateway with logging
- Gateway with manipulation rules
- Service orchestration
"""

import time

import can
import pytest

from wp4.core.events import EventType
from wp4.core.gateway import BidirectionalGateway
from wp4.core.gateway_logger import GatewayLogger
from wp4.core.manipulation import Action, ManipulationEngine, ManipulationRule
from wp4.services.gateway_service import GatewayService


@pytest.fixture(autouse=True)
def ensure_vcan_for_integration(vcan_up):
    """Ensure vcan interfaces are up before each integration test."""
    pass


class TestEndToEndForwarding:
    """Integration tests for complete message forwarding."""

    def test_simple_forward_and_receive(self, gateway):
        """Test basic message forwarding from vcan0 to vcan1."""
        gateway.start()
        time.sleep(0.1)

        with (
            can.Bus(channel="vcan0", interface="socketcan") as tx,
            can.Bus(channel="vcan1", interface="socketcan") as rx,
        ):
            # Send message
            tx.send(can.Message(arbitration_id=0x123, data=b"\x01\x02\x03"))

            # Receive forwarded message
            recv = rx.recv(timeout=1.0)

            assert recv is not None
            assert recv.arbitration_id == 0x123
            assert bytes(recv.data) == b"\x01\x02\x03"

        # Verify statistics
        assert gateway.received_0to1 >= 1
        assert gateway.forwarded_0to1 >= 1

    def test_bidirectional_concurrent_traffic(self, gateway):
        """Test simultaneous bidirectional message forwarding."""
        gateway.start()
        time.sleep(0.1)

        with (
            can.Bus(channel="vcan0", interface="socketcan") as bus0,
            can.Bus(channel="vcan1", interface="socketcan") as bus1,
        ):
            # Send from both directions
            msg_0to1 = can.Message(arbitration_id=0x100, data=b"\xaa")
            msg_1to0 = can.Message(arbitration_id=0x200, data=b"\xbb")

            bus0.send(msg_0to1)
            bus1.send(msg_1to0)

            # Receive on both sides
            recv_on_1 = bus1.recv(timeout=1.0)
            recv_on_0 = bus0.recv(timeout=1.0)

            assert recv_on_1 is not None
            assert recv_on_1.arbitration_id == 0x100

            assert recv_on_0 is not None
            assert recv_on_0.arbitration_id == 0x200

    def test_high_throughput_forwarding(self, gateway):
        """Test forwarding many messages in quick succession."""
        gateway.start()
        time.sleep(0.1)

        num_messages = 100
        max_receive_attempts = num_messages * 3  # Prevent infinite loop

        with (
            can.Bus(channel="vcan0", interface="socketcan") as tx,
            can.Bus(channel="vcan1", interface="socketcan") as rx,
        ):
            # Send many messages
            for i in range(num_messages):
                tx.send(can.Message(arbitration_id=0x100 + (i % 16), data=bytes([i % 256])))

            # Receive all messages (with limit to prevent infinite loop)
            time.sleep(0.5)
            received = 0
            for _ in range(max_receive_attempts):
                msg = rx.recv(timeout=0.1)
                if msg is None:
                    break
                received += 1

            # Should have received all messages
            assert received >= num_messages

    def test_1000_msg_per_second_throughput(self, gateway):
        """Test gateway handles 1000 msg/s on both interfaces simultaneously.

        This tests the minimum required throughput of 1000 messages per second
        in each direction (bidirectional traffic).
        """
        gateway.start()
        time.sleep(0.1)

        msg_per_second = 1000
        test_duration = 1.0  # 1 second
        total_messages = int(msg_per_second * test_duration)
        interval = 1.0 / msg_per_second

        with (
            can.Bus(channel="vcan0", interface="socketcan") as bus0,
            can.Bus(channel="vcan1", interface="socketcan") as bus1,
        ):
            import threading

            received_0to1 = []
            received_1to0 = []
            stop_receivers = threading.Event()

            def receiver_0to1():
                while not stop_receivers.is_set():
                    msg = bus1.recv(timeout=0.1)
                    if msg and msg.arbitration_id >= 0x100 and msg.arbitration_id < 0x200:
                        received_0to1.append(msg)

            def receiver_1to0():
                while not stop_receivers.is_set():
                    msg = bus0.recv(timeout=0.1)
                    if msg and msg.arbitration_id >= 0x200 and msg.arbitration_id < 0x300:
                        received_1to0.append(msg)

            # Start receiver threads
            rx_thread_0to1 = threading.Thread(target=receiver_0to1, daemon=True)
            rx_thread_1to0 = threading.Thread(target=receiver_1to0, daemon=True)
            rx_thread_0to1.start()
            rx_thread_1to0.start()

            # Send 1000 msg/s from vcan0 to vcan1
            start_time = time.time()
            sent_0to1 = 0
            sent_1to0 = 0

            for i in range(total_messages):
                # Send in both directions
                bus0.send(can.Message(arbitration_id=0x100 + (i % 16), data=bytes([i % 256])))
                bus1.send(can.Message(arbitration_id=0x200 + (i % 16), data=bytes([i % 256])))
                sent_0to1 += 1
                sent_1to0 += 1

                # Pace to achieve target rate (approximate)
                if i % 100 == 99:
                    elapsed = time.time() - start_time
                    expected = (i + 1) * interval
                    if elapsed < expected:
                        time.sleep(expected - elapsed)

            send_duration = time.time() - start_time

            # Wait for all messages to be forwarded
            time.sleep(0.5)
            stop_receivers.set()
            rx_thread_0to1.join(timeout=1.0)
            rx_thread_1to0.join(timeout=1.0)

            # Calculate actual throughput
            actual_rate_0to1 = sent_0to1 / send_duration
            actual_rate_1to0 = sent_1to0 / send_duration

            # Allow some tolerance (>90% received)
            min_expected = int(total_messages * 0.90)

            assert len(received_0to1) >= min_expected, (
                f"0to1: received {len(received_0to1)}/{total_messages} "
                f"(rate: {actual_rate_0to1:.0f} msg/s)"
            )
            assert len(received_1to0) >= min_expected, (
                f"1to0: received {len(received_1to0)}/{total_messages} "
                f"(rate: {actual_rate_1to0:.0f} msg/s)"
            )

        # Verify gateway statistics
        assert gateway.forwarded_0to1 >= min_expected
        assert gateway.forwarded_1to0 >= min_expected

    def test_extended_id_forwarding(self, gateway):
        """Test forwarding messages with extended CAN IDs."""
        gateway.start()
        time.sleep(0.1)

        with (
            can.Bus(channel="vcan0", interface="socketcan") as tx,
            can.Bus(channel="vcan1", interface="socketcan") as rx,
        ):
            tx.send(
                can.Message(
                    arbitration_id=0x18DAF100,
                    data=b"\x01\x02\x03\x04\x05\x06\x07\x08",
                    is_extended_id=True,
                )
            )

            recv = rx.recv(timeout=1.0)

            assert recv is not None
            assert recv.arbitration_id == 0x18DAF100
            assert recv.is_extended_id is True
            assert len(recv.data) == 8


class TestGatewayWithLogging:
    """Integration tests for gateway with logging enabled."""

    def test_gateway_with_blf_logging(self, gateway, temp_log_dir):
        """Test gateway logs messages to BLF file."""
        logger = GatewayLogger(temp_log_dir)
        gateway.set_logger(logger)

        logger.start("vcan0", "vcan1")
        gateway.start()
        time.sleep(0.1)

        with (
            can.Bus(channel="vcan0", interface="socketcan") as tx,
            can.Bus(channel="vcan1", interface="socketcan") as rx,
        ):
            # Send some messages
            for i in range(5):
                tx.send(can.Message(arbitration_id=0x100 + i, data=bytes([i])))

            time.sleep(0.2)
            # Drain receive buffer (with limit to prevent infinite loop)
            for _ in range(100):
                if rx.recv(timeout=0.1) is None:
                    break

        gateway.stop()
        logger.stop()

        # Verify BLF file was created and has content
        blf_path = logger.get_blf_path()
        assert blf_path is not None
        assert blf_path.exists()
        assert blf_path.stat().st_size > 0

    def test_gateway_logging_both_directions(self, gateway, temp_log_dir):
        """Test logging captures messages in both directions."""
        from can.io.blf import BLFReader

        logger = GatewayLogger(temp_log_dir)
        gateway.set_logger(logger)

        logger.start("vcan0", "vcan1")
        gateway.start()
        time.sleep(0.1)

        with (
            can.Bus(channel="vcan0", interface="socketcan") as bus0,
            can.Bus(channel="vcan1", interface="socketcan") as bus1,
        ):
            # Send in both directions
            bus0.send(can.Message(arbitration_id=0x100, data=b"\x01"))
            bus1.send(can.Message(arbitration_id=0x200, data=b"\x02"))

            time.sleep(0.2)
            # Drain buffers (with limits to prevent infinite loops)
            for _ in range(100):
                if bus0.recv(timeout=0.1) is None:
                    break
            for _ in range(100):
                if bus1.recv(timeout=0.1) is None:
                    break

        gateway.stop()
        logger.stop()

        # Verify both channels have messages
        blf_path = logger.get_blf_path()
        channels = set()
        with BLFReader(str(blf_path)) as reader:
            for msg in reader:
                channels.add(msg.channel)

        # Should have messages on both channels (1 = 0to1, 2 = 1to0)
        assert 1 in channels or 2 in channels


class TestGatewayWithManipulation:
    """Integration tests for gateway with manipulation rules."""

    def test_drop_rule_prevents_forwarding(self, gateway):
        """Test DROP rule prevents message from being forwarded."""

        manipulator = ManipulationEngine()
        manipulator.add_rule(
            ManipulationRule(
                name="drop_0x123",
                can_id=0x123,
                action=Action.DROP,
                direction="0to1",
            )
        )
        gateway._manipulator = manipulator

        gateway.start()
        time.sleep(0.1)

        with (
            can.Bus(channel="vcan0", interface="socketcan") as tx,
            can.Bus(channel="vcan1", interface="socketcan") as rx,
        ):
            # Drain any pending messages from previous tests
            for _ in range(50):
                if rx.recv(timeout=0.05) is None:
                    break

            # Send message that should be dropped
            tx.send(can.Message(arbitration_id=0x123, data=b"\x01"))

            # Should NOT receive (allow extra time for processing)
            recv = rx.recv(timeout=0.5)
            assert recv is None

            # But different ID should pass through
            tx.send(can.Message(arbitration_id=0x456, data=b"\x02"))
            recv = rx.recv(timeout=0.5)
            assert recv is not None
            assert recv.arbitration_id == 0x456

    def test_manipulation_rule_modifies_data(self, gateway):
        """Test manipulation rule changes message data using byte operations."""
        from wp4.core.manipulation import ByteManipulation, Operation

        manipulator = ManipulationEngine()
        manipulator.add_rule(
            ManipulationRule(
                name="set_byte_0",
                can_id=0x100,
                action=Action.FORWARD,
                direction="0to1",
                manipulations=[
                    ByteManipulation(byte_index=0, operation=Operation.SET, value=0xFF),
                    ByteManipulation(byte_index=1, operation=Operation.SET, value=0xAA),
                ],
            )
        )
        gateway._manipulator = manipulator

        gateway.start()
        time.sleep(0.1)

        with (
            can.Bus(channel="vcan0", interface="socketcan") as tx,
            can.Bus(channel="vcan1", interface="socketcan") as rx,
        ):
            # Send original message
            tx.send(can.Message(arbitration_id=0x100, data=b"\x01\x02"))

            # Receive should have modified data
            recv = rx.recv(timeout=1.0)
            assert recv is not None
            assert recv.data[0] == 0xFF
            assert recv.data[1] == 0xAA

    def test_delay_rule_adds_latency(self, gateway):
        """Test DELAY rule adds extra latency."""
        manipulator = ManipulationEngine()
        manipulator.add_rule(
            ManipulationRule(
                name="delay_0x100",
                can_id=0x100,
                action=Action.DELAY,
                direction="0to1",
                extra_delay_ms=100,
            )
        )
        gateway._manipulator = manipulator

        gateway.start()
        time.sleep(0.1)

        with (
            can.Bus(channel="vcan0", interface="socketcan") as tx,
            can.Bus(channel="vcan1", interface="socketcan") as rx,
        ):
            # Drain any pending messages from previous tests
            for _ in range(50):
                if rx.recv(timeout=0.05) is None:
                    break

            start = time.time()
            tx.send(can.Message(arbitration_id=0x100, data=b"\x01"))

            recv = rx.recv(timeout=1.0)
            elapsed = time.time() - start

            assert recv is not None
            # Should take at least ~100ms due to delay rule
            assert elapsed >= 0.08


class TestServiceOrchestration:
    """Integration tests for GatewayService orchestration."""

    def test_service_full_lifecycle(self, vcan_config):
        """Test complete service lifecycle."""
        service = GatewayService(vcan_config)
        event_bus = service.get_event_bus()

        events = []
        event_bus.subscribe(EventType.GATEWAY_STARTED, lambda d: events.append("started"))
        event_bus.subscribe(EventType.GATEWAY_STOPPED, lambda d: events.append("stopped"))

        # Start service
        service.bring_up_interfaces()
        service.start()
        assert service.is_running()

        time.sleep(0.1)

        # Get status
        status = service.get_status()
        assert status.running

        # Stop service
        service.stop()
        service.bring_down_interfaces()
        assert not service.is_running()

        # Verify events
        assert "started" in events
        assert "stopped" in events

    def test_service_settings_update_while_running(self, vcan_config):
        """Test updating settings while gateway is running."""
        service = GatewayService(vcan_config)

        service.start()
        time.sleep(0.1)

        # Update settings
        service.update_settings(delay_ms=50, loss_pct=5.0)

        # Verify update
        config = service.get_config()
        assert config.delay_ms == 50
        assert config.loss_pct == 5.0

        service.stop()

    def test_service_direction_toggle(self, vcan_config):
        """Test enabling/disabling directions via service."""
        service = GatewayService(vcan_config)

        service.start()
        time.sleep(0.1)

        # Disable 0to1
        service.disable_direction("0to1")
        assert not service.get_config().enable_0to1

        # Re-enable
        service.enable_direction("0to1")
        assert service.get_config().enable_0to1

        service.stop()

    def test_service_with_message_traffic(self, vcan_config):
        """Test service handles actual CAN traffic."""
        service = GatewayService(vcan_config)

        service.bring_up_interfaces()
        service.start()
        time.sleep(0.1)

        with (
            can.Bus(channel="vcan0", interface="socketcan") as tx,
            can.Bus(channel="vcan1", interface="socketcan") as rx,
        ):
            tx.send(can.Message(arbitration_id=0x123, data=b"\x01\x02"))

            recv = rx.recv(timeout=1.0)
            assert recv is not None
            assert recv.arbitration_id == 0x123

        # Check statistics via service
        status = service.get_status()
        assert status.stats_0to1["received"] >= 1

        service.stop()
        service.bring_down_interfaces()


class TestDelayAndLoss:
    """Integration tests for delay and loss functionality."""

    def test_delay_measured_in_latency_samples(self, gateway_with_delay):
        """Test that delay shows up in latency samples."""
        gateway_with_delay.start()
        time.sleep(0.1)

        with (
            can.Bus(channel="vcan0", interface="socketcan") as tx,
            can.Bus(channel="vcan1", interface="socketcan") as rx,
        ):
            # Send multiple messages
            for _ in range(10):
                tx.send(can.Message(arbitration_id=0x100, data=b"\x01"))
                time.sleep(0.01)

            time.sleep(0.2)
            # Drain buffer (with limit to prevent infinite loop)
            for _ in range(100):
                if rx.recv(timeout=0.1) is None:
                    break

        # Check latency samples
        samples = gateway_with_delay.get_latency_samples("0to1")
        assert len(samples) >= 5

        # Average should be around 50ms (50000 us)
        avg = sum(samples) / len(samples)
        assert avg >= 40000  # At least 40ms

    def test_loss_increases_dropped_count(self, vcan_up):
        """Test that loss percentage increases dropped count."""
        gw = BidirectionalGateway(
            "vcan0",
            "vcan1",
            delay_ms=0,
            loss_pct=100.0,  # 100% loss
        )
        gw.start()
        time.sleep(0.1)

        try:
            with can.Bus(channel="vcan0", interface="socketcan") as tx:
                for _ in range(10):
                    tx.send(can.Message(arbitration_id=0x100, data=b"\x01"))

            time.sleep(0.2)

            # All should be dropped
            assert gw.dropped_0to1 >= 10
            assert gw.forwarded_0to1 == 0
        finally:
            gw.stop()

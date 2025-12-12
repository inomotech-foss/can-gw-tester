"""Bidirectional CAN gateway with delay and packet loss - core business logic."""

import heapq
import random
import threading
import time
from typing import TYPE_CHECKING

import can

from wp4.core.bus_factory import BusFactory, get_default_factory
from wp4.core.direction_stats import DirectionStats, create_direction_pair

if TYPE_CHECKING:
    from can import BusABC

    from wp4.core.gateway_logger import GatewayLogger
    from wp4.core.manipulation import ManipulationEngine


class BidirectionalGateway:
    """Bidirectional CAN gateway with delay and packet loss.

    Uses a single socket per interface with receive_own_messages=False to prevent
    forwarded messages from being looped back. This eliminates the need for
    software-based deduplication.

    Architecture:
    - One Bus object per interface (shared for send/receive)
    - Two receiver threads (one per interface)
    - Two sender threads (one per direction)
    - Messages received on bus0 are queued for sending on bus1 (and vice versa)
    - Per-direction state encapsulated in DirectionStats dataclass
    """

    MAX_QUEUE_SIZE = 10000  # Drop oldest if queue exceeds this

    def __init__(
        self,
        iface0: str,
        iface1: str,
        delay_ms: int = 0,
        loss_pct: float = 0.0,
        jitter_ms: float = 0.0,
        logger: "GatewayLogger | None" = None,
        manipulator: "ManipulationEngine | None" = None,
        bus_factory: BusFactory | None = None,
    ):
        self._iface0 = iface0
        self._iface1 = iface1
        self._delay_ms = delay_ms
        self._loss_pct = loss_pct
        self._jitter_ms = max(0.0, jitter_ms)
        self._logger = logger
        self._manipulator = manipulator
        self._bus_factory = bus_factory or get_default_factory()
        self._running = False

        # Shared bus objects (one per interface)
        self._bus0: BusABC | None = None
        self._bus1: BusABC | None = None

        # Threads
        self._recv_thread_0: threading.Thread | None = None
        self._recv_thread_1: threading.Thread | None = None
        self._send_thread_0to1: threading.Thread | None = None
        self._send_thread_1to0: threading.Thread | None = None

        # Per-direction statistics and state (encapsulated in DirectionStats)
        self._stats_0to1, self._stats_1to0 = create_direction_pair()

        # Locks for thread-safe access to DirectionStats fields
        self._stats_lock = threading.Lock()  # Protects counters
        self._direction_lock = threading.Lock()  # Protects enabled flag
        self._latency_lock = threading.Lock()  # Protects latency samples

    @property
    def delay_ms(self) -> int:
        return self._delay_ms

    @delay_ms.setter
    def delay_ms(self, value: int):
        self._delay_ms = value

    @property
    def loss_pct(self) -> float:
        return self._loss_pct

    @loss_pct.setter
    def loss_pct(self, value: float):
        self._loss_pct = value

    @property
    def jitter_ms(self) -> float:
        return self._jitter_ms

    @jitter_ms.setter
    def jitter_ms(self, value: float):
        self._jitter_ms = max(0.0, value)

    def set_logger(self, logger: "GatewayLogger | None") -> None:
        """Set or remove the logger dynamically.

        Can be called while gateway is running to enable/disable logging.

        Args:
            logger: GatewayLogger instance, or None to disable logging
        """
        self._logger = logger

    @property
    def is_running(self) -> bool:
        """Check if gateway is currently running.

        Use this property instead of accessing _running directly.
        """
        return self._running

    def _get_stats(self, direction: str) -> DirectionStats:
        """Get DirectionStats for the specified direction."""
        return self._stats_0to1 if direction == "0to1" else self._stats_1to0

    # Statistics properties for 0→1 direction (thread-safe reads)
    @property
    def received_0to1(self) -> int:
        with self._stats_lock:
            return self._stats_0to1.received

    @property
    def forwarded_0to1(self) -> int:
        with self._stats_lock:
            return self._stats_0to1.forwarded

    @property
    def dropped_0to1(self) -> int:
        with self._stats_lock:
            return self._stats_0to1.dropped

    @property
    def queue_size_0to1(self) -> int:
        return self._stats_0to1.queue_size

    # Statistics properties for 1→0 direction (thread-safe reads)
    @property
    def received_1to0(self) -> int:
        with self._stats_lock:
            return self._stats_1to0.received

    @property
    def forwarded_1to0(self) -> int:
        with self._stats_lock:
            return self._stats_1to0.forwarded

    @property
    def dropped_1to0(self) -> int:
        with self._stats_lock:
            return self._stats_1to0.dropped

    @property
    def queue_size_1to0(self) -> int:
        return self._stats_1to0.queue_size

    def _increment_received(self, direction: str) -> None:
        """Thread-safe increment of received counter."""
        with self._stats_lock:
            stats = self._get_stats(direction)
            stats.received += 1

    def _increment_forwarded(self, direction: str) -> None:
        """Thread-safe increment of forwarded counter."""
        with self._stats_lock:
            stats = self._get_stats(direction)
            stats.forwarded += 1

    def _increment_dropped(self, direction: str) -> None:
        """Thread-safe increment of dropped counter."""
        with self._stats_lock:
            stats = self._get_stats(direction)
            stats.dropped += 1

    def get_latency_samples(self, direction: str) -> list[float]:
        """Get latency samples for a direction (in microseconds)."""
        with self._latency_lock:
            stats = self._get_stats(direction)
            return list(stats.latency_samples)

    def clear_latency_samples(self):
        """Clear all latency samples."""
        with self._latency_lock:
            self._stats_0to1.clear_latency_samples()
            self._stats_1to0.clear_latency_samples()

    def set_direction_enabled(self, direction: str, enabled: bool):
        """Enable or disable a specific direction ('0to1' or '1to0').

        Thread-safe: Uses _direction_lock to prevent race conditions with _receive_loop.
        """
        with self._direction_lock:
            stats = self._get_stats(direction)
            stats.enabled = enabled

    def start(self):
        """Start the bidirectional gateway."""
        if self._running:
            return

        self._running = True

        # Reset all direction statistics
        self._stats_0to1.reset_all()
        self._stats_1to0.reset_all()

        # Create shared bus objects with receive_own_messages=False
        # This is the key: we won't receive messages we send ourselves!
        self._bus0 = self._bus_factory.create_bus(
            channel=self._iface0,
            receive_own_messages=False,
        )
        self._bus1 = self._bus_factory.create_bus(
            channel=self._iface1,
            receive_own_messages=False,
        )

        # Start receiver threads
        self._recv_thread_0 = threading.Thread(
            target=self._receive_loop, args=(self._bus0, "0to1"), daemon=True
        )
        self._recv_thread_1 = threading.Thread(
            target=self._receive_loop, args=(self._bus1, "1to0"), daemon=True
        )

        # Start sender threads
        self._send_thread_0to1 = threading.Thread(
            target=self._send_loop, args=(self._bus1, "0to1"), daemon=True
        )
        self._send_thread_1to0 = threading.Thread(
            target=self._send_loop, args=(self._bus0, "1to0"), daemon=True
        )

        self._recv_thread_0.start()
        self._recv_thread_1.start()
        self._send_thread_0to1.start()
        self._send_thread_1to0.start()

    def stop(self):
        """Stop the gateway and clean up resources."""
        self._running = False

        # Wake up sender threads (notify_all to ensure all waiting threads wake up)
        with self._stats_0to1.condition:
            self._stats_0to1.condition.notify_all()
        with self._stats_1to0.condition:
            self._stats_1to0.condition.notify_all()

        # Wait for threads to finish with increased timeout
        threads = [
            self._recv_thread_0,
            self._recv_thread_1,
            self._send_thread_0to1,
            self._send_thread_1to0,
        ]
        for thread in threads:
            if thread and thread.is_alive():
                thread.join(timeout=2.0)

        # Shutdown buses only after threads have stopped
        if self._bus0:
            self._bus0.shutdown()
            self._bus0 = None
        if self._bus1:
            self._bus1.shutdown()
            self._bus1 = None

        self._recv_thread_0 = None
        self._recv_thread_1 = None
        self._send_thread_0to1 = None
        self._send_thread_1to0 = None

    def _receive_loop(self, bus: "BusABC", direction: str):
        """Receive messages and schedule them for delayed forwarding.

        Args:
            bus: The bus to receive from
            direction: '0to1' or '1to0'
        """
        stats = self._get_stats(direction)

        while self._running:
            try:
                msg = bus.recv(timeout=0.1)
                if msg is None:
                    continue

                # Check if this direction is enabled (thread-safe read)
                with self._direction_lock:
                    direction_enabled = stats.enabled
                if not direction_enabled:
                    continue

                # Update received counter (thread-safe)
                recv_time = time.time()
                msg_data = bytes(msg.data)
                self._increment_received(direction)

                # Log RX event
                if self._logger:
                    self._logger.log_rx(
                        direction, recv_time, msg.arbitration_id, msg_data, msg.is_extended_id
                    )

                # Apply manipulation rules
                extra_delay = 0.0
                if self._manipulator:
                    from wp4.core.manipulation import Action

                    action, msg_data, extra_delay = self._manipulator.process(
                        msg.arbitration_id, msg_data, direction
                    )
                    if action == Action.DROP:
                        self._increment_dropped(direction)
                        if self._logger:
                            self._logger.log_drop(
                                direction,
                                recv_time,
                                msg.arbitration_id,
                                msg_data,
                                msg.is_extended_id,
                            )
                        continue

                # Simulate packet loss
                if self._loss_pct > 0 and random.random() * 100 < self._loss_pct:
                    self._increment_dropped(direction)
                    # Log DROP event
                    if self._logger:
                        self._logger.log_drop(
                            direction, recv_time, msg.arbitration_id, msg_data, msg.is_extended_id
                        )
                    continue

                # Schedule for delayed sending with optional jitter
                base_delay = self._delay_ms / 1000.0
                jitter = (
                    random.uniform(-self._jitter_ms, self._jitter_ms) / 1000.0
                    if self._jitter_ms > 0
                    else 0.0
                )
                # Include extra delay from manipulation rules
                rule_delay = extra_delay / 1000.0
                # Ensure send_time is never before recv_time
                send_time = max(recv_time + base_delay + jitter + rule_delay, recv_time)

                with stats.condition:
                    # Drop oldest if queue is too large
                    while stats.queue_size >= self.MAX_QUEUE_SIZE:
                        heapq.heappop(stats.queue)
                        self._increment_dropped(direction)

                    heapq.heappush(
                        stats.queue,
                        (
                            send_time,
                            recv_time,
                            msg.arbitration_id,
                            msg_data,
                            msg.is_extended_id,
                        ),
                    )
                    stats.condition.notify()

                    # Log QUEUE event
                    if self._logger:
                        self._logger.log_queue(
                            direction,
                            recv_time,
                            msg.arbitration_id,
                            msg_data,
                            msg.is_extended_id,
                            send_time,
                        )

            except Exception:
                if not self._running:
                    break

    def _send_loop(self, bus: "BusABC", direction: str):
        """Send scheduled messages when their time comes.

        Args:
            bus: The bus to send to
            direction: '0to1' or '1to0'
        """
        stats = self._get_stats(direction)

        while self._running:
            msg_to_send = None
            recv_time = None

            with stats.condition:
                while self._running:
                    now = time.time()

                    if not stats.queue:
                        stats.condition.wait(timeout=0.5)
                        continue

                    next_send_time = stats.queue[0][0]
                    wait_time = next_send_time - now

                    if wait_time <= 0:
                        send_time, recv_time, arb_id, data, is_ext = heapq.heappop(stats.queue)
                        msg_to_send = can.Message(
                            arbitration_id=arb_id,
                            data=data,
                            is_extended_id=is_ext,
                        )
                        break
                    else:
                        stats.condition.wait(timeout=wait_time)

            if msg_to_send:
                assert recv_time is not None  # recv_time is set when msg_to_send is set
                try:
                    bus.send(msg_to_send)
                    actual_send_time = time.time()

                    # Record actual latency (in microseconds)
                    latency_us = (actual_send_time - recv_time) * 1_000_000
                    with self._latency_lock:
                        stats.latency_samples.append(latency_us)

                    self._increment_forwarded(direction)

                    # Log TX event
                    if self._logger:
                        self._logger.log_tx(
                            direction,
                            actual_send_time,
                            msg_to_send.arbitration_id,
                            bytes(msg_to_send.data),
                            msg_to_send.is_extended_id,
                            latency_us,
                        )
                except Exception:
                    self._increment_dropped(direction)

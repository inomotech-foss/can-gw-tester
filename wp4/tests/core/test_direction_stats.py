"""Tests for DirectionStats dataclass."""

import heapq
import time

from wp4.core.direction_stats import DirectionStats, create_direction_pair


class TestDirectionStats:
    """Tests for DirectionStats dataclass."""

    def test_init_default_values(self):
        """Test default initialization."""
        stats = DirectionStats(direction="0to1")

        assert stats.direction == "0to1"
        assert stats.received == 0
        assert stats.forwarded == 0
        assert stats.dropped == 0
        assert stats.queue == []
        assert stats.enabled is True
        assert len(stats.latency_samples) == 0

    def test_init_custom_direction(self):
        """Test initialization with different direction."""
        stats = DirectionStats(direction="1to0")
        assert stats.direction == "1to0"

    def test_reset_counters(self):
        """Test counter reset."""
        stats = DirectionStats(direction="0to1")
        stats.received = 100
        stats.forwarded = 90
        stats.dropped = 10

        stats.reset_counters()

        assert stats.received == 0
        assert stats.forwarded == 0
        assert stats.dropped == 0

    def test_clear_queue(self):
        """Test queue clearing."""
        stats = DirectionStats(direction="0to1")
        stats.queue.append((1.0, 0.9, 0x123, b"\x01", False))
        stats.queue.append((2.0, 1.9, 0x456, b"\x02", False))

        assert len(stats.queue) == 2

        stats.clear_queue()

        assert len(stats.queue) == 0

    def test_clear_latency_samples(self):
        """Test latency samples clearing."""
        stats = DirectionStats(direction="0to1")
        stats.latency_samples.append(1000.0)
        stats.latency_samples.append(2000.0)

        assert len(stats.latency_samples) == 2

        stats.clear_latency_samples()

        assert len(stats.latency_samples) == 0

    def test_reset_all(self):
        """Test full reset."""
        stats = DirectionStats(direction="0to1")
        stats.received = 100
        stats.queue.append((1.0, 0.9, 0x123, b"\x01", False))
        stats.latency_samples.append(1000.0)

        stats.reset_all()

        assert stats.received == 0
        assert len(stats.queue) == 0
        assert len(stats.latency_samples) == 0

    def test_queue_size_property(self):
        """Test queue_size property."""
        stats = DirectionStats(direction="0to1")

        assert stats.queue_size == 0

        stats.queue.append((1.0, 0.9, 0x123, b"\x01", False))
        assert stats.queue_size == 1

        stats.queue.append((2.0, 1.9, 0x456, b"\x02", False))
        assert stats.queue_size == 2

    def test_queue_as_priority_queue(self):
        """Test using queue as priority queue with heapq."""
        stats = DirectionStats(direction="0to1")

        # Push items in non-sorted order
        heapq.heappush(stats.queue, (3.0, 2.9, 0x100, b"\x01", False))
        heapq.heappush(stats.queue, (1.0, 0.9, 0x200, b"\x02", False))
        heapq.heappush(stats.queue, (2.0, 1.9, 0x300, b"\x03", False))

        # Pop should return in sorted order by send_time
        item1 = heapq.heappop(stats.queue)
        assert item1[0] == 1.0
        assert item1[2] == 0x200

        item2 = heapq.heappop(stats.queue)
        assert item2[0] == 2.0
        assert item2[2] == 0x300

        item3 = heapq.heappop(stats.queue)
        assert item3[0] == 3.0
        assert item3[2] == 0x100

    def test_condition_variable(self):
        """Test condition variable exists and is usable."""
        stats = DirectionStats(direction="0to1")

        # Should be able to acquire and release
        with stats.condition:
            pass

    def test_latency_samples_maxlen(self):
        """Test latency samples has maxlen of 100."""
        stats = DirectionStats(direction="0to1")

        # Add 150 samples
        for i in range(150):
            stats.latency_samples.append(float(i))

        # Should only have 100
        assert len(stats.latency_samples) == 100

        # Oldest should be dropped (0-49 gone, 50-149 remain)
        assert min(stats.latency_samples) == 50.0
        assert max(stats.latency_samples) == 149.0

    def test_get_latency_stats_empty(self):
        """Test latency stats with no samples."""
        stats = DirectionStats(direction="0to1")
        result = stats.get_latency_stats()

        assert result["min"] is None
        assert result["max"] is None
        assert result["avg"] is None
        assert result["p95"] is None
        assert result["p99"] is None

    def test_get_latency_stats_with_samples(self):
        """Test latency stats calculation."""
        stats = DirectionStats(direction="0to1")

        # Add 100 samples: 0, 1, 2, ..., 99 (in microseconds)
        for i in range(100):
            stats.latency_samples.append(float(i))

        result = stats.get_latency_stats()

        assert result["min"] == 0.0
        assert result["max"] == 99.0
        assert result["avg"] == 49.5
        assert result["p95"] == 95.0
        assert result["p99"] == 99.0

    def test_to_dict(self):
        """Test dictionary conversion."""
        stats = DirectionStats(direction="0to1")
        stats.received = 100
        stats.forwarded = 90
        stats.dropped = 10
        stats.enabled = True
        stats.queue.append((1.0, 0.9, 0x123, b"\x01", False))

        result = stats.to_dict()

        assert result["direction"] == "0to1"
        assert result["received"] == 100
        assert result["forwarded"] == 90
        assert result["dropped"] == 10
        assert result["queue_size"] == 1
        assert result["enabled"] is True
        assert "latency_stats" in result

    def test_enabled_flag(self):
        """Test enabled flag toggling."""
        stats = DirectionStats(direction="0to1")

        assert stats.enabled is True

        stats.enabled = False
        assert stats.enabled is False

        stats.enabled = True
        assert stats.enabled is True


class TestCreateDirectionPair:
    """Tests for create_direction_pair helper."""

    def test_creates_two_stats(self):
        """Test that it creates two DirectionStats."""
        stats_0to1, stats_1to0 = create_direction_pair()

        assert isinstance(stats_0to1, DirectionStats)
        assert isinstance(stats_1to0, DirectionStats)

    def test_correct_directions(self):
        """Test that directions are correctly set."""
        stats_0to1, stats_1to0 = create_direction_pair()

        assert stats_0to1.direction == "0to1"
        assert stats_1to0.direction == "1to0"

    def test_independent_instances(self):
        """Test that instances are independent."""
        stats_0to1, stats_1to0 = create_direction_pair()

        stats_0to1.received = 100
        stats_1to0.received = 200

        assert stats_0to1.received == 100
        assert stats_1to0.received == 200

    def test_separate_queues(self):
        """Test that queues are separate."""
        stats_0to1, stats_1to0 = create_direction_pair()

        stats_0to1.queue.append((1.0, 0.9, 0x100, b"\x01", False))

        assert len(stats_0to1.queue) == 1
        assert len(stats_1to0.queue) == 0

    def test_separate_conditions(self):
        """Test that condition variables are separate."""
        stats_0to1, stats_1to0 = create_direction_pair()

        # Should be different objects
        assert stats_0to1.condition is not stats_1to0.condition


class TestThreadSafety:
    """Tests for thread-safe usage patterns."""

    def test_condition_wait_notify(self):
        """Test condition variable wait/notify pattern."""
        import threading

        stats = DirectionStats(direction="0to1")
        received_items = []

        def producer():
            time.sleep(0.01)
            with stats.condition:
                stats.queue.append((1.0, 0.9, 0x123, b"\x01", False))
                stats.condition.notify()

        def consumer():
            with stats.condition:
                while not stats.queue:
                    stats.condition.wait(timeout=1.0)
                if stats.queue:
                    item = stats.queue.pop(0)
                    received_items.append(item)

        consumer_thread = threading.Thread(target=consumer)
        producer_thread = threading.Thread(target=producer)

        consumer_thread.start()
        producer_thread.start()

        consumer_thread.join(timeout=2.0)
        producer_thread.join(timeout=2.0)

        assert len(received_items) == 1
        assert received_items[0][2] == 0x123

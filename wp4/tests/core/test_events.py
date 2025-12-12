"""Unit tests for EventBus and Direction enum."""

import pytest

from wp4.core.events import Direction, EventBus, EventType


def test_event_bus_subscribe_and_publish():
    """Test subscribing to events and publishing them."""
    bus = EventBus()
    events = []

    def handler(data):
        events.append(data)

    bus.subscribe(EventType.GATEWAY_STARTED, handler)
    bus.publish(EventType.GATEWAY_STARTED, {"test": "data"})

    assert len(events) == 1
    assert events[0] == {"test": "data"}


def test_event_bus_multiple_subscribers():
    """Test multiple subscribers to the same event."""
    bus = EventBus()
    events1 = []
    events2 = []

    bus.subscribe(EventType.GATEWAY_STARTED, lambda d: events1.append(d))
    bus.subscribe(EventType.GATEWAY_STARTED, lambda d: events2.append(d))

    bus.publish(EventType.GATEWAY_STARTED, {"msg": "hello"})

    assert len(events1) == 1
    assert len(events2) == 1
    assert events1[0] == {"msg": "hello"}
    assert events2[0] == {"msg": "hello"}


def test_event_bus_different_event_types():
    """Test that different event types don't interfere."""
    bus = EventBus()
    started_events = []
    stopped_events = []

    bus.subscribe(EventType.GATEWAY_STARTED, lambda d: started_events.append(d))
    bus.subscribe(EventType.GATEWAY_STOPPED, lambda d: stopped_events.append(d))

    bus.publish(EventType.GATEWAY_STARTED, {"data": 1})
    bus.publish(EventType.GATEWAY_STOPPED, {"data": 2})

    assert len(started_events) == 1
    assert len(stopped_events) == 1
    assert started_events[0] == {"data": 1}
    assert stopped_events[0] == {"data": 2}


def test_event_bus_unsubscribe():
    """Test unsubscribing from events."""
    bus = EventBus()
    events = []

    def handler(data):
        events.append(data)

    bus.subscribe(EventType.GATEWAY_STARTED, handler)
    bus.publish(EventType.GATEWAY_STARTED, {"test": 1})

    bus.unsubscribe(EventType.GATEWAY_STARTED, handler)
    bus.publish(EventType.GATEWAY_STARTED, {"test": 2})

    # Only the first event should be recorded
    assert len(events) == 1
    assert events[0] == {"test": 1}


def test_event_bus_publish_with_no_subscribers():
    """Test publishing to an event with no subscribers doesn't crash."""
    bus = EventBus()
    # Should not raise an exception
    bus.publish(EventType.GATEWAY_STARTED, {"data": "test"})


def test_event_bus_exception_in_handler_doesnt_break_others():
    """Test that an exception in one handler doesn't prevent others from running."""
    bus = EventBus()
    events = []

    def bad_handler(data):
        raise ValueError("Handler error")

    def good_handler(data):
        events.append(data)

    bus.subscribe(EventType.GATEWAY_STARTED, bad_handler)
    bus.subscribe(EventType.GATEWAY_STARTED, good_handler)

    bus.publish(EventType.GATEWAY_STARTED, {"msg": "test"})

    # Good handler should still run despite bad handler exception
    assert len(events) == 1
    assert events[0] == {"msg": "test"}


def test_event_bus_publish_none_data():
    """Test publishing event with None data."""
    bus = EventBus()
    events = []

    bus.subscribe(EventType.GATEWAY_STOPPED, lambda d: events.append(d))
    bus.publish(EventType.GATEWAY_STOPPED)

    assert len(events) == 1
    assert events[0] is None


# Direction enum tests


class TestDirection:
    """Tests for Direction enum."""

    def test_direction_values(self):
        """Test Direction enum has correct string values."""
        assert Direction.ZERO_TO_ONE.value == "0to1"
        assert Direction.ONE_TO_ZERO.value == "1to0"
        assert Direction.BOTH.value == "both"

    def test_direction_str(self):
        """Test Direction.__str__ returns the value."""
        assert str(Direction.ZERO_TO_ONE) == "0to1"
        assert str(Direction.ONE_TO_ZERO) == "1to0"
        assert str(Direction.BOTH) == "both"

    def test_direction_from_string(self):
        """Test Direction.from_string converts strings to enum."""
        assert Direction.from_string("0to1") == Direction.ZERO_TO_ONE
        assert Direction.from_string("1to0") == Direction.ONE_TO_ZERO
        assert Direction.from_string("both") == Direction.BOTH

    def test_direction_from_string_invalid(self):
        """Test Direction.from_string raises ValueError for invalid strings."""
        with pytest.raises(ValueError, match="Invalid direction"):
            Direction.from_string("invalid")

    def test_direction_comparison_with_value(self):
        """Test Direction enum can be compared using .value."""
        direction = "0to1"
        assert Direction.ZERO_TO_ONE.value == direction

    def test_direction_in_dict_key(self):
        """Test Direction enum .value can be used as dict key."""
        data = {
            Direction.ZERO_TO_ONE.value: "data_0to1",
            Direction.ONE_TO_ZERO.value: "data_1to0",
        }
        assert data["0to1"] == "data_0to1"
        assert data["1to0"] == "data_1to0"

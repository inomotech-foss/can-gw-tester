"""Tests for CAN message manipulation module."""

from wp4.core.manipulation import (
    Action,
    ByteManipulation,
    ManipulationEngine,
    ManipulationRule,
    Operation,
)


class TestByteManipulation:
    """Tests for ByteManipulation class."""

    def test_set_operation(self):
        """SET replaces byte with value."""
        data = bytearray([0x00, 0x11, 0x22, 0x33])
        manip = ByteManipulation(byte_index=1, operation=Operation.SET, value=0xFF)
        manip.apply(data)
        assert data == bytearray([0x00, 0xFF, 0x22, 0x33])

    def test_and_operation(self):
        """AND performs bitwise AND."""
        data = bytearray([0xFF, 0xAB, 0x00])
        manip = ByteManipulation(byte_index=1, operation=Operation.AND, value=0xF0)
        manip.apply(data)
        assert data == bytearray([0xFF, 0xA0, 0x00])

    def test_or_operation(self):
        """OR performs bitwise OR."""
        data = bytearray([0x00, 0x0F, 0x00])
        manip = ByteManipulation(byte_index=1, operation=Operation.OR, value=0xF0)
        manip.apply(data)
        assert data == bytearray([0x00, 0xFF, 0x00])

    def test_xor_operation(self):
        """XOR performs bitwise XOR."""
        data = bytearray([0x00, 0xFF, 0x00])
        manip = ByteManipulation(byte_index=1, operation=Operation.XOR, value=0x0F)
        manip.apply(data)
        assert data == bytearray([0x00, 0xF0, 0x00])

    def test_add_operation(self):
        """ADD adds value with wraparound."""
        data = bytearray([0x00, 0x10, 0x00])
        manip = ByteManipulation(byte_index=1, operation=Operation.ADD, value=0x05)
        manip.apply(data)
        assert data == bytearray([0x00, 0x15, 0x00])

    def test_add_operation_wraparound(self):
        """ADD wraps around at 255."""
        data = bytearray([0x00, 0xFE, 0x00])
        manip = ByteManipulation(byte_index=1, operation=Operation.ADD, value=0x05)
        manip.apply(data)
        assert data == bytearray([0x00, 0x03, 0x00])

    def test_sub_operation(self):
        """SUB subtracts value with wraparound."""
        data = bytearray([0x00, 0x10, 0x00])
        manip = ByteManipulation(byte_index=1, operation=Operation.SUB, value=0x05)
        manip.apply(data)
        assert data == bytearray([0x00, 0x0B, 0x00])

    def test_sub_operation_wraparound(self):
        """SUB wraps around at 0."""
        data = bytearray([0x00, 0x02, 0x00])
        manip = ByteManipulation(byte_index=1, operation=Operation.SUB, value=0x05)
        manip.apply(data)
        assert data == bytearray([0x00, 0xFD, 0x00])

    def test_out_of_bounds_index_ignored(self):
        """Out of bounds index is safely ignored."""
        data = bytearray([0x00, 0x11])
        manip = ByteManipulation(byte_index=5, operation=Operation.SET, value=0xFF)
        manip.apply(data)
        assert data == bytearray([0x00, 0x11])

    def test_value_masked_to_byte(self):
        """Values larger than 255 are masked to byte."""
        data = bytearray([0x00])
        manip = ByteManipulation(byte_index=0, operation=Operation.SET, value=0x1FF)
        manip.apply(data)
        assert data == bytearray([0xFF])


class TestManipulationRule:
    """Tests for ManipulationRule class."""

    def test_matches_exact_id(self):
        """Exact ID match works."""
        rule = ManipulationRule(name="test", can_id=0x123)
        assert rule.matches(0x123, "0to1")
        assert not rule.matches(0x124, "0to1")

    def test_matches_any_id(self):
        """ID -1 matches any ID."""
        rule = ManipulationRule(name="test", can_id=-1)
        assert rule.matches(0x000, "0to1")
        assert rule.matches(0x123, "0to1")
        assert rule.matches(0x7FF, "0to1")

    def test_matches_with_mask(self):
        """ID matching with mask works."""
        # Match any ID where lower nibble is 0x3
        rule = ManipulationRule(name="test", can_id=0x003, can_id_mask=0x00F)
        assert rule.matches(0x003, "0to1")
        assert rule.matches(0x123, "0to1")
        assert rule.matches(0x7F3, "0to1")
        assert not rule.matches(0x124, "0to1")

    def test_matches_direction_0to1(self):
        """Direction 0to1 only matches 0to1."""
        rule = ManipulationRule(name="test", can_id=0x123, direction="0to1")
        assert rule.matches(0x123, "0to1")
        assert not rule.matches(0x123, "1to0")

    def test_matches_direction_1to0(self):
        """Direction 1to0 only matches 1to0."""
        rule = ManipulationRule(name="test", can_id=0x123, direction="1to0")
        assert not rule.matches(0x123, "0to1")
        assert rule.matches(0x123, "1to0")

    def test_matches_direction_both(self):
        """Direction both matches either direction."""
        rule = ManipulationRule(name="test", can_id=0x123, direction="both")
        assert rule.matches(0x123, "0to1")
        assert rule.matches(0x123, "1to0")

    def test_disabled_rule_never_matches(self):
        """Disabled rules never match."""
        rule = ManipulationRule(name="test", can_id=0x123, enabled=False)
        assert not rule.matches(0x123, "0to1")

    def test_apply_drop(self):
        """DROP action returns drop and original data."""
        rule = ManipulationRule(name="test", can_id=0x123, action=Action.DROP)
        action, data, delay = rule.apply(b"\x01\x02\x03")
        assert action == Action.DROP
        assert data == b"\x01\x02\x03"
        assert delay == 0.0

    def test_apply_forward_no_manipulation(self):
        """FORWARD without manipulation returns original data."""
        rule = ManipulationRule(name="test", can_id=0x123, action=Action.FORWARD)
        action, data, delay = rule.apply(b"\x01\x02\x03")
        assert action == Action.FORWARD
        assert data == b"\x01\x02\x03"
        assert delay == 0.0

    def test_apply_forward_with_manipulation(self):
        """FORWARD with manipulation modifies data."""
        manip = ByteManipulation(byte_index=1, operation=Operation.SET, value=0xFF)
        rule = ManipulationRule(
            name="test",
            can_id=0x123,
            action=Action.FORWARD,
            manipulations=[manip],
        )
        action, data, delay = rule.apply(b"\x01\x02\x03")
        assert action == Action.FORWARD
        assert data == b"\x01\xff\x03"
        assert delay == 0.0

    def test_apply_delay(self):
        """DELAY action returns extra delay."""
        rule = ManipulationRule(
            name="test",
            can_id=0x123,
            action=Action.DELAY,
            extra_delay_ms=100.0,
        )
        action, data, delay = rule.apply(b"\x01\x02\x03")
        assert action == Action.FORWARD
        assert data == b"\x01\x02\x03"
        assert delay == 100.0

    def test_apply_multiple_manipulations(self):
        """Multiple byte manipulations are applied in order."""
        manipulations = [
            ByteManipulation(byte_index=0, operation=Operation.SET, value=0xAA),
            ByteManipulation(byte_index=1, operation=Operation.OR, value=0xF0),
            ByteManipulation(byte_index=2, operation=Operation.AND, value=0x0F),
        ]
        rule = ManipulationRule(
            name="test",
            can_id=0x123,
            manipulations=manipulations,
        )
        action, data, delay = rule.apply(b"\x00\x0f\xff")
        assert action == Action.FORWARD
        assert data == b"\xaa\xff\x0f"


class TestManipulationEngine:
    """Tests for ManipulationEngine class."""

    def test_init_empty(self):
        """Engine starts with no rules."""
        engine = ManipulationEngine()
        assert engine.get_rules() == []
        assert engine.enabled

    def test_add_rule(self):
        """Add rule works."""
        engine = ManipulationEngine()
        rule = ManipulationRule(name="test", can_id=0x123)
        engine.add_rule(rule)
        assert len(engine.get_rules()) == 1
        assert engine.get_rules()[0].name == "test"

    def test_remove_rule(self):
        """Remove rule by name works."""
        engine = ManipulationEngine()
        engine.add_rule(ManipulationRule(name="rule1", can_id=0x100))
        engine.add_rule(ManipulationRule(name="rule2", can_id=0x200))

        assert engine.remove_rule("rule1")
        assert len(engine.get_rules()) == 1
        assert engine.get_rules()[0].name == "rule2"

    def test_remove_nonexistent_rule(self):
        """Remove nonexistent rule returns False."""
        engine = ManipulationEngine()
        assert not engine.remove_rule("nonexistent")

    def test_clear_rules(self):
        """Clear rules removes all rules."""
        engine = ManipulationEngine()
        engine.add_rule(ManipulationRule(name="rule1", can_id=0x100))
        engine.add_rule(ManipulationRule(name="rule2", can_id=0x200))

        engine.clear_rules()
        assert engine.get_rules() == []

    def test_set_rules(self):
        """Set rules replaces all rules."""
        engine = ManipulationEngine()
        engine.add_rule(ManipulationRule(name="old", can_id=0x100))

        new_rules = [
            ManipulationRule(name="new1", can_id=0x200),
            ManipulationRule(name="new2", can_id=0x300),
        ]
        engine.set_rules(new_rules)

        names = [r.name for r in engine.get_rules()]
        assert names == ["new1", "new2"]

    def test_process_no_rules(self):
        """Process with no rules forwards unchanged."""
        engine = ManipulationEngine()
        action, data, delay = engine.process(0x123, b"\x01\x02", "0to1")
        assert action == Action.FORWARD
        assert data == b"\x01\x02"
        assert delay == 0.0

    def test_process_matching_rule(self):
        """Process applies first matching rule."""
        engine = ManipulationEngine()
        engine.add_rule(
            ManipulationRule(
                name="drop",
                can_id=0x123,
                action=Action.DROP,
            )
        )

        action, data, delay = engine.process(0x123, b"\x01\x02", "0to1")
        assert action == Action.DROP

    def test_process_first_match_wins(self):
        """First matching rule is applied."""
        engine = ManipulationEngine()
        engine.add_rule(
            ManipulationRule(
                name="first",
                can_id=0x123,
                action=Action.DROP,
            )
        )
        engine.add_rule(
            ManipulationRule(
                name="second",
                can_id=0x123,
                manipulations=[ByteManipulation(byte_index=0, operation=Operation.SET, value=0xFF)],
            )
        )

        # First rule should drop, second should never be reached
        action, data, delay = engine.process(0x123, b"\x01\x02", "0to1")
        assert action == Action.DROP
        assert data == b"\x01\x02"

    def test_process_no_match_forwards(self):
        """Non-matching message is forwarded unchanged."""
        engine = ManipulationEngine()
        engine.add_rule(ManipulationRule(name="test", can_id=0x123))

        action, data, delay = engine.process(0x456, b"\x01\x02", "0to1")
        assert action == Action.FORWARD
        assert data == b"\x01\x02"

    def test_enabled_toggle(self):
        """Disabled engine forwards all messages."""
        engine = ManipulationEngine()
        engine.add_rule(ManipulationRule(name="drop", can_id=0x123, action=Action.DROP))

        # Enabled: should drop
        assert engine.enabled
        action, _, _ = engine.process(0x123, b"\x01", "0to1")
        assert action == Action.DROP

        # Disabled: should forward
        engine.enabled = False
        assert not engine.enabled
        action, _, _ = engine.process(0x123, b"\x01", "0to1")
        assert action == Action.FORWARD

    def test_get_matching_rule(self):
        """Get matching rule returns first match."""
        engine = ManipulationEngine()
        rule1 = ManipulationRule(name="rule1", can_id=0x100)
        rule2 = ManipulationRule(name="rule2", can_id=0x123)
        engine.add_rule(rule1)
        engine.add_rule(rule2)

        match = engine.get_matching_rule(0x123, "0to1")
        assert match is not None
        assert match.name == "rule2"

    def test_get_matching_rule_none(self):
        """Get matching rule returns None when no match."""
        engine = ManipulationEngine()
        engine.add_rule(ManipulationRule(name="test", can_id=0x123))

        assert engine.get_matching_rule(0x456, "0to1") is None

    def test_get_matching_rule_disabled(self):
        """Get matching rule returns None when disabled."""
        engine = ManipulationEngine()
        engine.add_rule(ManipulationRule(name="test", can_id=0x123))
        engine.enabled = False

        assert engine.get_matching_rule(0x123, "0to1") is None


class TestManipulationIntegration:
    """Integration tests for manipulation scenarios."""

    def test_charge_power_limit(self):
        """Simulate limiting charge power by clamping byte value."""
        # Rule: Set byte 2 to max 0x10 (16) to limit charge power
        rule = ManipulationRule(
            name="limit_charge",
            can_id=0x6B0,  # Typical charge message ID
            manipulations=[ByteManipulation(byte_index=2, operation=Operation.SET, value=0x10)],
        )
        engine = ManipulationEngine()
        engine.add_rule(rule)

        # Original message requests high power (0xFF)
        original = bytes([0x00, 0x00, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00])
        action, data, _ = engine.process(0x6B0, original, "0to1")

        assert action == Action.FORWARD
        assert data[2] == 0x10  # Power limited

    def test_block_specific_can_id(self):
        """Block messages with specific CAN ID."""
        rule = ManipulationRule(
            name="block_diagnostics",
            can_id=0x7DF,  # OBD-II broadcast
            action=Action.DROP,
        )
        engine = ManipulationEngine()
        engine.add_rule(rule)

        action, _, _ = engine.process(0x7DF, b"\x02\x01\x00", "0to1")
        assert action == Action.DROP

        # Other messages pass through
        action, _, _ = engine.process(0x123, b"\x01\x02\x03", "0to1")
        assert action == Action.FORWARD

    def test_modify_bit_flags(self):
        """Modify specific bit flags using AND/OR."""
        # Clear bit 7, set bit 0
        rule = ManipulationRule(
            name="modify_flags",
            can_id=0x200,
            manipulations=[
                ByteManipulation(byte_index=0, operation=Operation.AND, value=0x7F),
                ByteManipulation(byte_index=0, operation=Operation.OR, value=0x01),
            ],
        )
        engine = ManipulationEngine()
        engine.add_rule(rule)

        # Original: bit 7 set, bit 0 clear (0x80)
        action, data, _ = engine.process(0x200, bytes([0x80, 0x00]), "0to1")

        # Result: bit 7 clear, bit 0 set (0x01)
        assert data[0] == 0x01

    def test_direction_specific_rules(self):
        """Different rules for different directions."""
        engine = ManipulationEngine()

        # Drop 0x123 going 0->1
        engine.add_rule(
            ManipulationRule(name="drop_0to1", can_id=0x123, direction="0to1", action=Action.DROP)
        )

        # Modify 0x123 going 1->0
        engine.add_rule(
            ManipulationRule(
                name="modify_1to0",
                can_id=0x123,
                direction="1to0",
                manipulations=[ByteManipulation(byte_index=0, operation=Operation.SET, value=0xAA)],
            )
        )

        # 0->1 should be dropped
        action, _, _ = engine.process(0x123, b"\x00", "0to1")
        assert action == Action.DROP

        # 1->0 should be modified
        action, data, _ = engine.process(0x123, b"\x00", "1to0")
        assert action == Action.FORWARD
        assert data == b"\xaa"

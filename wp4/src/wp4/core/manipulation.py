"""CAN message manipulation rules.

Provides filtering and data manipulation for CAN messages passing through
the gateway. Supports ID filtering, byte-level operations, and configurable
masks for testing ECU behavior under modified traffic.
"""

from dataclasses import dataclass, field
from enum import Enum


class Operation(Enum):
    """Byte manipulation operations."""

    SET = "set"  # Replace byte with value
    AND = "and"  # Bitwise AND with value
    OR = "or"  # Bitwise OR with value
    XOR = "xor"  # Bitwise XOR with value
    ADD = "add"  # Add value (with wraparound)
    SUB = "sub"  # Subtract value (with wraparound)


class Action(Enum):
    """What to do with matching messages."""

    FORWARD = "forward"  # Forward (possibly modified)
    DROP = "drop"  # Drop the message
    DELAY = "delay"  # Add extra delay


@dataclass
class ByteManipulation:
    """A single byte manipulation."""

    byte_index: int  # Which byte to modify (0-7)
    operation: Operation  # Operation to perform
    value: int  # Value for operation (0-255)

    def apply(self, data: bytearray) -> None:
        """Apply manipulation to data."""
        if self.byte_index >= len(data):
            return

        original = data[self.byte_index]

        if self.operation == Operation.SET:
            data[self.byte_index] = self.value & 0xFF
        elif self.operation == Operation.AND:
            data[self.byte_index] = original & self.value
        elif self.operation == Operation.OR:
            data[self.byte_index] = original | self.value
        elif self.operation == Operation.XOR:
            data[self.byte_index] = original ^ self.value
        elif self.operation == Operation.ADD:
            data[self.byte_index] = (original + self.value) & 0xFF
        elif self.operation == Operation.SUB:
            data[self.byte_index] = (original - self.value) & 0xFF


@dataclass
class ManipulationRule:
    """A rule for filtering and manipulating CAN messages.

    Example rules:
    - Limit charge power: match ID 0x123, set byte[2] = 0x10
    - Block specific ID: match ID 0x456, action = DROP
    - Mask bits: match ID 0x789, AND byte[0] with 0xF0
    """

    name: str  # Human-readable name
    can_id: int  # CAN ID to match (-1 for any)
    can_id_mask: int = 0x7FF  # Mask for ID matching (0x7FF = exact match)
    direction: str = "both"  # "0to1", "1to0", or "both"
    action: Action = Action.FORWARD
    manipulations: list[ByteManipulation] = field(default_factory=list)
    enabled: bool = True
    extra_delay_ms: float = 0.0  # For Action.DELAY

    def matches(self, arb_id: int, msg_direction: str) -> bool:
        """Check if this rule matches the message.

        Args:
            arb_id: Message arbitration ID
            msg_direction: Direction of the message ("0to1" or "1to0")

        Returns:
            True if rule matches this message
        """
        if not self.enabled:
            return False

        # Check direction
        if self.direction != "both" and self.direction != msg_direction:
            return False

        # Check ID (with mask) - return False if ID doesn't match
        if self.can_id >= 0:
            return (arb_id & self.can_id_mask) == (self.can_id & self.can_id_mask)

        return True

    def apply(self, data: bytes) -> tuple[Action, bytes, float]:
        """Apply rule to message data.

        Args:
            data: Original message data

        Returns:
            Tuple of (action, modified_data, extra_delay_ms)
        """
        if self.action == Action.DROP:
            return (Action.DROP, data, 0.0)

        # Apply byte manipulations
        modified = bytearray(data)
        for manip in self.manipulations:
            manip.apply(modified)

        extra_delay = self.extra_delay_ms if self.action == Action.DELAY else 0.0
        return (Action.FORWARD, bytes(modified), extra_delay)


class ManipulationEngine:
    """Engine for applying manipulation rules to CAN messages.

    Rules are evaluated in order. First matching rule wins.
    If no rules match, message is forwarded unchanged.
    """

    def __init__(self):
        self._rules: list[ManipulationRule] = []
        self._enabled = True

    @property
    def enabled(self) -> bool:
        """Check if manipulation is enabled."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Enable or disable manipulation."""
        self._enabled = value

    def add_rule(self, rule: ManipulationRule) -> None:
        """Add a rule to the engine."""
        self._rules.append(rule)

    def remove_rule(self, name: str) -> bool:
        """Remove a rule by name.

        Returns:
            True if rule was found and removed
        """
        for i, rule in enumerate(self._rules):
            if rule.name == name:
                del self._rules[i]
                return True
        return False

    def clear_rules(self) -> None:
        """Remove all rules."""
        self._rules.clear()

    def get_rules(self) -> list[ManipulationRule]:
        """Get all rules."""
        return list(self._rules)

    def set_rules(self, rules: list[ManipulationRule]) -> None:
        """Replace all rules."""
        self._rules = list(rules)

    def process(self, arb_id: int, data: bytes, direction: str) -> tuple[Action, bytes, float]:
        """Process a message through the rules.

        Args:
            arb_id: Message arbitration ID
            data: Message data bytes
            direction: Direction ("0to1" or "1to0")

        Returns:
            Tuple of (action, modified_data, extra_delay_ms)
        """
        if not self._enabled:
            return (Action.FORWARD, data, 0.0)

        for rule in self._rules:
            if rule.matches(arb_id, direction):
                return rule.apply(data)

        # No matching rule - forward unchanged
        return (Action.FORWARD, data, 0.0)

    def get_matching_rule(self, arb_id: int, direction: str) -> ManipulationRule | None:
        """Get the first matching rule for a message.

        Args:
            arb_id: Message arbitration ID
            direction: Direction ("0to1" or "1to0")

        Returns:
            Matching rule or None
        """
        if not self._enabled:
            return None

        for rule in self._rules:
            if rule.matches(arb_id, direction):
                return rule

        return None

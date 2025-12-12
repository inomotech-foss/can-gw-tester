"""CAN Message Manipulation Widget.

Provides UI for configuring message filtering and byte manipulation rules.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from wp4.core.manipulation import (
    Action,
    ByteManipulation,
    ManipulationRule,
    Operation,
)
from wp4.services.gateway_service import GatewayService


class ByteManipulationDialog(QDialog):
    """Dialog for editing a byte manipulation."""

    def __init__(self, parent=None, manipulation: ByteManipulation | None = None):
        super().__init__(parent)
        self.setWindowTitle("Byte Manipulation")
        self.setMinimumWidth(300)

        layout = QFormLayout(self)

        # Byte index
        self._byte_index = QSpinBox()
        self._byte_index.setRange(0, 7)
        layout.addRow("Byte Index:", self._byte_index)

        # Operation
        self._operation = QComboBox()
        for op in Operation:
            self._operation.addItem(op.value, op)
        layout.addRow("Operation:", self._operation)

        # Value
        self._value = QSpinBox()
        self._value.setRange(0, 255)
        self._value.setPrefix("0x")
        self._value.setDisplayIntegerBase(16)
        layout.addRow("Value:", self._value)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        # Load existing manipulation
        if manipulation:
            self._byte_index.setValue(manipulation.byte_index)
            self._operation.setCurrentIndex(self._operation.findData(manipulation.operation))
            self._value.setValue(manipulation.value)

    def get_manipulation(self) -> ByteManipulation:
        """Get the configured manipulation."""
        return ByteManipulation(
            byte_index=self._byte_index.value(),
            operation=self._operation.currentData(),
            value=self._value.value(),
        )


class RuleDialog(QDialog):
    """Dialog for editing a manipulation rule."""

    def __init__(self, parent=None, rule: ManipulationRule | None = None):
        super().__init__(parent)
        self.setWindowTitle("Manipulation Rule")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # Basic settings
        basic_group = QGroupBox("Basic Settings")
        basic_layout = QFormLayout(basic_group)

        self._name = QLineEdit()
        self._name.setPlaceholderText("e.g., Limit Charge Power")
        basic_layout.addRow("Name:", self._name)

        # CAN ID
        id_layout = QHBoxLayout()
        self._can_id = QLineEdit()
        self._can_id.setPlaceholderText("e.g., 0x123 or -1 for any")
        id_layout.addWidget(self._can_id)
        id_layout.addWidget(QLabel("Mask:"))
        self._can_id_mask = QLineEdit()
        self._can_id_mask.setText("0x7FF")
        self._can_id_mask.setMaximumWidth(80)
        id_layout.addWidget(self._can_id_mask)
        basic_layout.addRow("CAN ID:", id_layout)

        # Direction
        self._direction = QComboBox()
        self._direction.addItem("Both Directions", "both")
        self._direction.addItem("0 → 1 only", "0to1")
        self._direction.addItem("1 → 0 only", "1to0")
        basic_layout.addRow("Direction:", self._direction)

        # Action
        self._action = QComboBox()
        self._action.addItem("Forward (modify)", Action.FORWARD)
        self._action.addItem("Drop", Action.DROP)
        self._action.addItem("Add Extra Delay", Action.DELAY)
        self._action.currentIndexChanged.connect(self._on_action_changed)
        basic_layout.addRow("Action:", self._action)

        # Extra delay (for DELAY action)
        self._extra_delay = QSpinBox()
        self._extra_delay.setRange(0, 10000)
        self._extra_delay.setSuffix(" ms")
        self._extra_delay.setEnabled(False)
        basic_layout.addRow("Extra Delay:", self._extra_delay)

        # Enabled
        self._enabled = QCheckBox("Enabled")
        self._enabled.setChecked(True)
        basic_layout.addRow("", self._enabled)

        layout.addWidget(basic_group)

        # Byte manipulations
        manip_group = QGroupBox("Byte Manipulations")
        manip_layout = QVBoxLayout(manip_group)

        self._manip_list = QListWidget()
        manip_layout.addWidget(self._manip_list)

        manip_btn_layout = QHBoxLayout()
        add_manip_btn = QPushButton("Add")
        add_manip_btn.clicked.connect(self._add_manipulation)
        edit_manip_btn = QPushButton("Edit")
        edit_manip_btn.clicked.connect(self._edit_manipulation)
        remove_manip_btn = QPushButton("Remove")
        remove_manip_btn.clicked.connect(self._remove_manipulation)
        manip_btn_layout.addWidget(add_manip_btn)
        manip_btn_layout.addWidget(edit_manip_btn)
        manip_btn_layout.addWidget(remove_manip_btn)
        manip_btn_layout.addStretch()
        manip_layout.addLayout(manip_btn_layout)

        layout.addWidget(manip_group)

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Store manipulations
        self._manipulations: list[ByteManipulation] = []

        # Load existing rule
        if rule:
            self._name.setText(rule.name)
            if rule.can_id >= 0:
                self._can_id.setText(f"0x{rule.can_id:03X}")
            else:
                self._can_id.setText("-1")
            self._can_id_mask.setText(f"0x{rule.can_id_mask:03X}")
            self._direction.setCurrentIndex(self._direction.findData(rule.direction))
            self._action.setCurrentIndex(self._action.findData(rule.action))
            self._extra_delay.setValue(int(rule.extra_delay_ms))
            self._enabled.setChecked(rule.enabled)
            self._manipulations = list(rule.manipulations)
            self._update_manip_list()

    def _on_action_changed(self, index: int) -> None:
        """Handle action change."""
        action = self._action.currentData()
        self._extra_delay.setEnabled(action == Action.DELAY)

    def _add_manipulation(self) -> None:
        """Add a new byte manipulation."""
        dialog = ByteManipulationDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._manipulations.append(dialog.get_manipulation())
            self._update_manip_list()

    def _edit_manipulation(self) -> None:
        """Edit selected manipulation."""
        row = self._manip_list.currentRow()
        if row >= 0:
            dialog = ByteManipulationDialog(self, self._manipulations[row])
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self._manipulations[row] = dialog.get_manipulation()
                self._update_manip_list()

    def _remove_manipulation(self) -> None:
        """Remove selected manipulation."""
        row = self._manip_list.currentRow()
        if row >= 0:
            del self._manipulations[row]
            self._update_manip_list()

    def _update_manip_list(self) -> None:
        """Update the manipulation list display."""
        self._manip_list.clear()
        for m in self._manipulations:
            text = f"byte[{m.byte_index}] {m.operation.value} 0x{m.value:02X}"
            self._manip_list.addItem(text)

    def get_rule(self) -> ManipulationRule:
        """Get the configured rule."""
        # Parse CAN ID
        can_id_text = self._can_id.text().strip()
        if can_id_text == "-1" or can_id_text == "":
            can_id = -1
        else:
            can_id = int(can_id_text, 16) if can_id_text.startswith("0x") else int(can_id_text)

        # Parse mask
        mask_text = self._can_id_mask.text().strip()
        can_id_mask = int(mask_text, 16) if mask_text.startswith("0x") else int(mask_text)

        return ManipulationRule(
            name=self._name.text() or "Unnamed Rule",
            can_id=can_id,
            can_id_mask=can_id_mask,
            direction=self._direction.currentData(),
            action=self._action.currentData(),
            manipulations=self._manipulations.copy(),
            enabled=self._enabled.isChecked(),
            extra_delay_ms=float(self._extra_delay.value()),
        )


class ManipulationWidget(QWidget):
    """Widget for managing CAN message manipulation rules."""

    rules_changed = Signal()

    def __init__(self, service: GatewayService):
        super().__init__()
        self._service = service
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Header with enable checkbox
        header_layout = QHBoxLayout()
        self._enabled_check = QCheckBox("Enable Manipulation")
        self._enabled_check.stateChanged.connect(self._on_enabled_changed)
        header_layout.addWidget(self._enabled_check)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Rules list
        rules_group = QGroupBox("Rules")
        rules_layout = QVBoxLayout(rules_group)

        self._rules_list = QListWidget()
        self._rules_list.itemDoubleClicked.connect(self._edit_rule)
        rules_layout.addWidget(self._rules_list)

        # Buttons
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add Rule")
        add_btn.clicked.connect(self._add_rule)
        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self._edit_rule)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_rule)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(edit_btn)
        btn_layout.addWidget(remove_btn)
        btn_layout.addStretch()
        rules_layout.addLayout(btn_layout)

        layout.addWidget(rules_group)

        # Quick add section
        quick_group = QGroupBox("Quick Add")
        quick_layout = QHBoxLayout(quick_group)

        quick_layout.addWidget(QLabel("Block ID:"))
        self._quick_block_id = QLineEdit()
        self._quick_block_id.setPlaceholderText("0x123")
        self._quick_block_id.setMaximumWidth(80)
        quick_layout.addWidget(self._quick_block_id)

        block_btn = QPushButton("Block")
        block_btn.clicked.connect(self._quick_block)
        quick_layout.addWidget(block_btn)

        quick_layout.addStretch()
        layout.addWidget(quick_group)

        # Initial sync
        self._sync_from_service()

    def _sync_from_service(self) -> None:
        """Sync UI from service state."""
        self._enabled_check.setChecked(self._service.is_manipulation_enabled())
        self._update_rules_list()

    def _update_rules_list(self) -> None:
        """Update the rules list display."""
        self._rules_list.clear()
        for rule in self._service.get_manipulation_rules():
            text = self._format_rule(rule)
            item = QListWidgetItem(text)
            if not rule.enabled:
                item.setForeground(item.foreground().color().darker())
            self._rules_list.addItem(item)

    def _format_rule(self, rule: ManipulationRule) -> str:
        """Format a rule for display."""
        id_str = f"0x{rule.can_id:03X}" if rule.can_id >= 0 else "ANY"
        dir_str = {"both": "⇄", "0to1": "→", "1to0": "←"}.get(rule.direction, "?")
        action_str = rule.action.value.upper()

        parts = [f"[{id_str}]", dir_str, action_str]
        if rule.manipulations:
            parts.append(f"({len(rule.manipulations)} ops)")
        if rule.name:
            parts.append(f"- {rule.name}")
        if not rule.enabled:
            parts.append("[disabled]")

        return " ".join(parts)

    def _on_enabled_changed(self, state: int) -> None:
        """Handle enabled checkbox change."""
        self._service.set_manipulation_enabled(bool(state))
        self.rules_changed.emit()

    def _add_rule(self) -> None:
        """Add a new rule."""
        dialog = RuleDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            rule = dialog.get_rule()
            self._service.add_manipulation_rule(rule)
            self._update_rules_list()
            self.rules_changed.emit()

    def _edit_rule(self) -> None:
        """Edit selected rule."""
        row = self._rules_list.currentRow()
        if row < 0:
            return

        rules = self._service.get_manipulation_rules()
        if row >= len(rules):
            return

        dialog = RuleDialog(self, rules[row])
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_rule = dialog.get_rule()
            # Replace rule
            rules[row] = new_rule
            self._service.set_manipulation_rules(rules)
            self._update_rules_list()
            self.rules_changed.emit()

    def _remove_rule(self) -> None:
        """Remove selected rule."""
        row = self._rules_list.currentRow()
        if row < 0:
            return

        rules = self._service.get_manipulation_rules()
        if row < len(rules):
            self._service.remove_manipulation_rule(rules[row].name)
            self._update_rules_list()
            self.rules_changed.emit()

    def _quick_block(self) -> None:
        """Quick add a blocking rule."""
        id_text = self._quick_block_id.text().strip()
        if not id_text:
            return

        try:
            can_id = int(id_text, 16) if id_text.startswith("0x") else int(id_text)
        except ValueError:
            return

        rule = ManipulationRule(
            name=f"Block 0x{can_id:03X}",
            can_id=can_id,
            action=Action.DROP,
        )
        self._service.add_manipulation_rule(rule)
        self._quick_block_id.clear()
        self._update_rules_list()
        self.rules_changed.emit()

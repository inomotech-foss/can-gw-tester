"""WP4 Shared Library for CAN Gateway.

This package provides utilities for CAN interface management.
"""

from .canif import (
    CanInterfaceState,
    get_interface_state,
    is_virtual_can,
    list_can_interfaces,
    load_can_gw_module,
    set_interface_down,
    set_interface_up,
)

__all__ = [
    "CanInterfaceState",
    "get_interface_state",
    "is_virtual_can",
    "list_can_interfaces",
    "load_can_gw_module",
    "set_interface_down",
    "set_interface_up",
]

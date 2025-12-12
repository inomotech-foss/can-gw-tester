"""CAN interface management using pyroute2/netlink with sudo fallback."""

import contextlib
import subprocess
from dataclasses import dataclass

from pyroute2 import IPRoute


@dataclass
class CanInterfaceState:
    """Current state of a CAN interface."""

    name: str
    index: int
    state: str  # "UP", "DOWN", "UNKNOWN"
    bitrate: int | None
    sample_point: float | None
    txqlen: int


def list_can_interfaces() -> list[str]:
    """List all CAN interfaces on the system."""
    with IPRoute() as ipr:
        links = ipr.get_links()
        can_interfaces = []
        for link in links:
            link_info = dict(link.get("attrs", []))
            if link_info.get("IFLA_LINKINFO"):
                info_data = dict(link_info["IFLA_LINKINFO"].get("attrs", []))
                if info_data.get("IFLA_INFO_KIND") == "can":
                    can_interfaces.append(link_info.get("IFLA_IFNAME", ""))
        return can_interfaces


def _get_interface_state_subprocess(name: str) -> CanInterfaceState | None:
    """Get interface state using ip command (fallback for asyncio conflicts)."""
    try:
        result = subprocess.run(
            ["ip", "-d", "link", "show", name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        output = result.stdout
        state = "DOWN"
        if "state UP" in output or ",UP" in output or "<UP," in output:
            state = "UP"

        bitrate = None
        for line in output.split("\n"):
            if "bitrate" in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "bitrate" and i + 1 < len(parts):
                        with contextlib.suppress(ValueError):
                            bitrate = int(parts[i + 1])
                        break

        return CanInterfaceState(
            name=name,
            index=0,
            state=state,
            bitrate=bitrate,
            sample_point=None,
            txqlen=0,
        )
    except Exception:
        return None


def get_interface_state(name: str) -> CanInterfaceState | None:
    """Get current state of a CAN interface."""
    # Use subprocess to avoid asyncio conflicts with pyroute2
    return _get_interface_state_subprocess(name)


def _run_ip_cmd(args: list[str]) -> None:
    """Run ip command with sudo."""
    result = subprocess.run(
        ["sudo", "-n", "ip"] + args,
        capture_output=True,
        timeout=10,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode().strip()
        raise OSError(f"ip command failed: {stderr}")


def is_virtual_can(name: str) -> bool:
    """Check if interface is a virtual CAN (vcan) interface."""
    return name.startswith("vcan")


def set_interface_up(name: str, bitrate: int = 500000) -> None:
    """Bring up a CAN interface with specified bitrate.

    For virtual CAN (vcan) interfaces, bitrate is ignored as vcan
    doesn't support bitrate configuration.

    Uses subprocess to avoid asyncio conflicts with pyroute2.
    """
    if is_virtual_can(name):
        # Virtual CAN doesn't need bitrate configuration
        _run_ip_cmd(["link", "set", name, "up"])
    else:
        # Real CAN interface - bring down first, then up with bitrate
        with contextlib.suppress(Exception):
            _run_ip_cmd(["link", "set", name, "down"])
        _run_ip_cmd(["link", "set", name, "up", "type", "can", "bitrate", str(bitrate)])


def set_interface_down(name: str) -> None:
    """Bring down a CAN interface.

    Uses subprocess to avoid asyncio conflicts with pyroute2.
    """
    _run_ip_cmd(["link", "set", name, "down"])


def load_can_gw_module() -> bool:
    """Load the can-gw kernel module."""
    try:
        result = subprocess.run(
            ["sudo", "-n", "modprobe", "can-gw"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False

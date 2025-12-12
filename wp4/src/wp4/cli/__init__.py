"""CAN Gateway CLI - Command line interface (redirects to GUI)."""

import click


@click.command()
@click.option("--vcan", "-v", is_flag=True, help="Use virtual CAN interfaces (vcan0, vcan1)")
@click.option("--iface0", "-0", default=None, help="First CAN interface (default: can0 or vcan0)")
@click.option("--iface1", "-1", default=None, help="Second CAN interface (default: can1 or vcan1)")
def main(vcan: bool, iface0: str | None, iface1: str | None) -> None:
    """CAN Gateway - Launches the GUI application.

    Start with --vcan for virtual CAN interfaces (development/testing).
    """
    # Import here to avoid circular imports and speed up CLI help
    import sys

    from wp4.gui import main as gui_main

    # Pass args to GUI
    if vcan and "--vcan" not in sys.argv:
        sys.argv.append("--vcan")
    gui_main()


__all__ = ["main"]

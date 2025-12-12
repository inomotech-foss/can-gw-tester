"""CAN Gateway GUI - PySide6 based graphical interface."""

import asyncio
import sys

import qasync
from PySide6.QtWidgets import QApplication

from wp4.gui.widgets.main_window import MainWindow


def main():
    """Main entry point for the CAN Gateway GUI."""
    app = QApplication(sys.argv)
    app.setApplicationName("CAN Gateway")
    app.setOrganizationName("WP4")

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Check for --vcan flag
    virtual = "--vcan" in sys.argv or "-v" in sys.argv

    window = MainWindow(virtual=virtual)
    window.show()

    with loop:
        loop.run_forever()


__all__ = ["main", "MainWindow"]

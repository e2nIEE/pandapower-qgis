"""
QGIS MessageBar wrapper for standardized user notifications.

This module provides a simple interface for displaying messages to users
through QGIS's MessageBar, ensuring consistent styling and behavior.

Usage:
    from .provider_utils import MessageManager

    MessageManager.show_error("Operation Failed", "Could not save file")
    MessageManager.show_success("Operation Complete", "File saved successfully")
"""

from qgis.core import Qgis
from qgis.utils import iface


class MessageManager:
    """
    Centralized message display manager for QGIS interface.
    Provides static methods for displaying different types of messages
    (error, warning, success, info) with consistent formatting and duration.
    """
    @staticmethod
    def show_error(title, message, duration=0):
        """
        Display an error message in QGIS message bar.

        Args:
            title (str): Message title (bold text)
            message (str): Detailed error message
            duration (int): Display duration in seconds (0 = until user closes)

        Example:
            MessageManager.show_error(
                "Network Load Failed",
                "Cannot load network from file: /path/to/file.json"
            )
        """
        if iface is None:
            return

        iface.messageBar().pushMessage(
            title,
            message,
            level=Qgis.Critical,
            duration=duration
        )

    @staticmethod
    def show_warning(title, message, duration=5):
        """
        Display a warning message in QGIS message bar.

        Args:
            title (str): Message title
            message (str): Warning message content
            duration (int): Display duration in seconds (default: 5)

        Example:
            MessageManager.show_warning(
                "Data Issue",
                "Some features could not be validated"
            )
        """
        if iface is None:
            return

        iface.messageBar().pushMessage(
            title,
            message,
            level=Qgis.Warning,
            duration=duration
        )

    @staticmethod
    def show_success(title, message, duration=3):
        """
        Display a success message in QGIS message bar.

        Args:
            title (str): Message title
            message (str): Success message content
            duration (int): Display duration in seconds (default: 3)

        Example:
            MessageManager.show_success(
                "Operation Complete",
                "5 features saved successfully"
            )
        """
        if iface is None:
            return

        iface.messageBar().pushMessage(
            title,
            message,
            level=Qgis.Success,
            duration=duration
        )

    @staticmethod
    def show_info(title, message, duration=5):
        """
        Display an informational message in QGIS message bar.

        Args:
            title (str): Message title
            message (str): Informational message content
            duration (int): Display duration in seconds (default: 5)

        Example:
            MessageManager.show_info(
                "Network Info",
                "Connected to network successfully"
            )
        """
        if iface is None:
            return

        iface.messageBar().pushMessage(
            title,
            message,
            level=Qgis.Info,
            duration=duration
        )

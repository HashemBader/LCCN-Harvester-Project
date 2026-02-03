"""
Module: notifications.py
Desktop notifications and system tray integration for LCCN Harvester.
"""
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import QObject, pyqtSignal
from pathlib import Path
import platform
import subprocess


class NotificationManager(QObject):
    """Manages desktop notifications and system tray."""

    notification_clicked = pyqtSignal()

    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self.system = platform.system()
        self.tray_icon = None
        self.notifications_enabled = True

    def setup_system_tray(self):
        """Setup system tray icon and menu."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("System tray not available")
            return

        # Create tray icon
        self.tray_icon = QSystemTrayIcon(self.main_window)

        # Try to load icon, fall back to default
        icon_path = Path(__file__).parent.parent.parent / "assets" / "icon.png"
        if icon_path.exists():
            self.tray_icon.setIcon(QIcon(str(icon_path)))
        else:
            # Use default Qt icon
            self.tray_icon.setIcon(self.main_window.style().standardIcon(
                self.main_window.style().StandardPixmap.SP_ComputerIcon
            ))

        self.tray_icon.setToolTip("LCCN Harvester")

        # Create context menu
        menu = QMenu()

        show_action = QAction("Show Window", self.main_window)
        show_action.triggered.connect(self._show_window)
        menu.addAction(show_action)

        menu.addSeparator()

        notifications_action = QAction("Enable Notifications", self.main_window)
        notifications_action.setCheckable(True)
        notifications_action.setChecked(True)
        notifications_action.triggered.connect(self._toggle_notifications)
        menu.addAction(notifications_action)

        menu.addSeparator()

        quit_action = QAction("Quit", self.main_window)
        quit_action.triggered.connect(self.main_window.close)
        menu.addAction(quit_action)

        self.tray_icon.setContextMenu(menu)

        # Connect double-click to show window
        self.tray_icon.activated.connect(self._on_tray_activated)

        # Show tray icon
        self.tray_icon.show()

    def _show_window(self):
        """Show and raise the main window."""
        if self.main_window:
            self.main_window.show()
            self.main_window.raise_()
            self.main_window.activateWindow()

    def _on_tray_activated(self, reason):
        """Handle tray icon activation."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()

    def _toggle_notifications(self, checked):
        """Toggle notifications on/off."""
        self.notifications_enabled = checked

    def show_notification(self, title, message, notification_type="info", duration=5000):
        """
        Show a desktop notification.

        Args:
            title: Notification title
            message: Notification message
            notification_type: Type of notification (info, success, warning, error)
            duration: Duration in milliseconds (default 5000 = 5 seconds)
        """
        if not self.notifications_enabled:
            return

        # Map notification types to icons
        icon_map = {
            "info": QSystemTrayIcon.MessageIcon.Information,
            "success": QSystemTrayIcon.MessageIcon.Information,
            "warning": QSystemTrayIcon.MessageIcon.Warning,
            "error": QSystemTrayIcon.MessageIcon.Critical
        }

        icon = icon_map.get(notification_type, QSystemTrayIcon.MessageIcon.Information)

        # Try system tray notification first (works on all platforms with Qt)
        if self.tray_icon and self.tray_icon.isVisible():
            self.tray_icon.showMessage(title, message, icon, duration)
        else:
            # Fall back to native notifications
            self._show_native_notification(title, message, notification_type)

    def _show_native_notification(self, title, message, notification_type):
        """Show native OS notification as fallback."""
        try:
            if self.system == "Darwin":  # macOS
                self._show_macos_notification(title, message)
            elif self.system == "Windows":
                self._show_windows_notification(title, message)
            elif self.system == "Linux":
                self._show_linux_notification(title, message)
        except Exception as e:
            print(f"Failed to show native notification: {e}")

    def _show_macos_notification(self, title, message):
        """Show macOS notification using osascript."""
        script = f'display notification "{message}" with title "{title}"'
        subprocess.run(["osascript", "-e", script], check=False)

    def _show_windows_notification(self, title, message):
        """Show Windows notification."""
        # Windows notifications through system tray should work
        # This is a fallback that could use win10toast if installed
        pass

    def _show_linux_notification(self, title, message):
        """Show Linux notification using notify-send."""
        subprocess.run(["notify-send", title, message], check=False)

    # Convenience methods for common notification types

    def notify_harvest_started(self, isbn_count):
        """Notify when harvest starts."""
        self.show_notification(
            "Harvest Started",
            f"Processing {isbn_count} ISBNs...",
            "info"
        )

    def notify_harvest_completed(self, stats):
        """Notify when harvest completes successfully."""
        found = stats.get('found', 0)
        failed = stats.get('failed', 0)
        total = stats.get('total', 0)

        message = f"✓ Found: {found}\n✗ Failed: {failed}\n━ Total: {total}"

        self.show_notification(
            "Harvest Complete!",
            message,
            "success",
            duration=8000
        )

    def notify_harvest_error(self, error_message):
        """Notify when harvest encounters an error."""
        self.show_notification(
            "Harvest Error",
            f"An error occurred: {error_message}",
            "error",
            duration=10000
        )

    def notify_milestone(self, milestone_type, value):
        """Notify when a milestone is reached."""
        messages = {
            "100_processed": f"🎯 Milestone: {value} ISBNs processed!",
            "500_processed": f"🚀 Milestone: {value} ISBNs processed!",
            "1000_processed": f"⭐ Milestone: {value} ISBNs processed!",
            "50_percent": f"📊 Progress: 50% complete ({value} ISBNs)",
            "75_percent": f"📊 Progress: 75% complete ({value} ISBNs)",
            "90_percent": f"📊 Progress: 90% complete - Almost done!",
        }

        message = messages.get(milestone_type, f"Milestone: {value}")

        self.show_notification(
            "Progress Update",
            message,
            "info",
            duration=3000
        )

    def notify_isbn_found(self, isbn, lccn):
        """Notify when an LCCN is found (optional, can be disabled for bulk)."""
        self.show_notification(
            "LCCN Found",
            f"ISBN {isbn}\n→ {lccn}",
            "success",
            duration=2000
        )

    def notify_cache_hit(self, count):
        """Notify about cache efficiency."""
        self.show_notification(
            "Cache Hit",
            f"⚡ {count} results loaded from cache",
            "info",
            duration=2000
        )

    def notify_api_error(self, api_name, error):
        """Notify when an API fails."""
        self.show_notification(
            f"{api_name} Error",
            f"API temporarily unavailable: {error}",
            "warning",
            duration=5000
        )

    def notify_export_complete(self, filename, record_count):
        """Notify when export completes."""
        self.show_notification(
            "Export Complete",
            f"✓ Exported {record_count} records\n→ {filename}",
            "success",
            duration=5000
        )


class NotificationPreferences:
    """Manage notification preferences."""

    def __init__(self):
        self.preferences_file = Path("data/notification_prefs.json")
        self.prefs = self._load_preferences()

    def _load_preferences(self):
        """Load notification preferences."""
        import json

        defaults = {
            "enabled": True,
            "show_milestones": True,
            "show_individual_finds": False,  # Disabled by default for bulk
            "show_cache_hits": False,
            "show_api_errors": True,
            "sound_enabled": False,
            "min_duration": 2000,
            "max_duration": 10000
        }

        try:
            if self.preferences_file.exists():
                with open(self.preferences_file) as f:
                    loaded = json.load(f)
                    defaults.update(loaded)
        except Exception:
            pass

        return defaults

    def save_preferences(self):
        """Save notification preferences."""
        import json

        try:
            self.preferences_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.preferences_file, 'w') as f:
                json.dump(self.prefs, f, indent=2)
        except Exception as e:
            print(f"Failed to save notification preferences: {e}")

    def set_preference(self, key, value):
        """Set a preference value."""
        self.prefs[key] = value
        self.save_preferences()

    def get_preference(self, key, default=None):
        """Get a preference value."""
        return self.prefs.get(key, default)

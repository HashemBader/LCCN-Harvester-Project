"""
Module: api_monitor_tab.py
API health monitoring and status display.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QGridLayout, QFrame, QPushButton, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from pathlib import Path
import sys
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from harvester.targets import create_target_from_config
from utils.targets_manager import TargetsManager


class APIStatusCard(QFrame):
    """Status card for a single API."""

    def __init__(self, name, enabled=True, compact=False):
        super().__init__()
        self.api_name = name
        self.enabled = enabled
        self.compact = compact
        self.last_check = None
        self.status = "unknown"  # unknown, online, offline, disabled
        self.response_time = None
        self.error_message = None
        self.rank = None
        self._setup_ui()

    def _setup_ui(self):
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setStyleSheet("""
            QFrame {
                background-color: #1b1c19;
                border: 1px solid #2d2e2b;
                border-left: 4px solid #666666;
                border-radius: 10px;
                padding: 14px;
            }
        """)

        layout = QVBoxLayout()

        # Header with name and status indicator
        header_layout = QHBoxLayout()

        # API name
        name_label = QLabel(self.api_name)
        name_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffffff; border: none;")
        header_layout.addWidget(name_label)

        header_layout.addStretch()

        # Status indicator
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("font-size: 24px; color: #666666; border: none;")
        header_layout.addWidget(self.status_indicator)

        layout.addLayout(header_layout)

        # Status text
        self.status_label = QLabel("Not checked")
        self.status_label.setStyleSheet("font-size: 11px; color: #aaaaaa; border: none;")
        layout.addWidget(self.status_label)

        self.active_label = QLabel("")
        self.active_label.setStyleSheet("font-size: 10px; border: none; font-weight: bold;")
        layout.addWidget(self.active_label)

        self.rank_label = QLabel("Rank: —")
        self.rank_label.setStyleSheet("font-size: 10px; color: #a7a59b; border: none;")
        layout.addWidget(self.rank_label)

        self.response_time_label = QLabel("")
        self.response_time_label.setStyleSheet("font-size: 10px; color: #888888; border: none;")
        self.last_check_label = QLabel("")
        self.last_check_label.setStyleSheet("font-size: 9px; color: #666666; border: none;")
        if not self.compact:
            layout.addWidget(self.response_time_label)
            layout.addWidget(self.last_check_label)

        self.setLayout(layout)

        # Update initial display
        self._update_display()

    def _update_display(self):
        """Update the visual display based on current status."""
        if not self.enabled:
            self.status = "disabled"
            color = "#ff4d4d"
            border_color = "#8f2e2e"
            status_text = "Inactive"
            self.active_label.setText("Inactive")
            self.active_label.setStyleSheet("font-size: 10px; color: #ff4d4d; border: none; font-weight: bold;")
            self.response_time_label.setText("")
        elif self.status == "online":
            color = "#00cc66"
            border_color = "#00cc66"
            status_text = "Online"
            self.active_label.setText("Active")
            self.active_label.setStyleSheet("font-size: 10px; color: #00cc66; border: none; font-weight: bold;")
            if self.response_time:
                self.response_time_label.setText(f"Response: {self.response_time:.2f}s")
        elif self.status == "offline":
            color = "#ff3333"
            border_color = "#ff3333"
            status_text = f"Offline"
            self.active_label.setText("Active")
            self.active_label.setStyleSheet("font-size: 10px; color: #00cc66; border: none; font-weight: bold;")
            if self.error_message:
                self.response_time_label.setText(f"Error: {self.error_message[:50]}")
        else:
            color = "#666666"
            border_color = "#666666"
            status_text = "Not checked"
            self.active_label.setText("Active")
            self.active_label.setStyleSheet("font-size: 10px; color: #00cc66; border: none; font-weight: bold;")
            self.response_time_label.setText("")

        self.status_indicator.setStyleSheet(f"font-size: 24px; color: {color}; border: none;")
        self.status_label.setText(status_text)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #1b1c19;
                border: 1px solid #2d2e2b;
                border-left: 4px solid {border_color};
                border-radius: 10px;
                padding: 14px;
            }}
        """)

        if self.last_check:
            self.last_check_label.setText(f"Last checked: {self.last_check.strftime('%H:%M:%S')}")
        self.rank_label.setText(f"Rank: {self.rank if self.rank is not None else '—'}")

    def update_status(self, online, response_time=None, error=None):
        """Update the API status."""
        self.last_check = datetime.now()
        self.status = "online" if online else "offline"
        self.response_time = response_time
        self.error_message = error
        self._update_display()

    def set_enabled(self, enabled):
        """Set whether this API is enabled."""
        self.enabled = enabled
        self._update_display()

    def set_rank(self, rank):
        """Set display rank for this API target."""
        self.rank = rank
        self._update_display()


class APICheckWorker(QThread):
    """Background worker for API health checks."""

    completed = pyqtSignal(dict)

    def __init__(self, api_names, timeout=3):
        super().__init__()
        self.api_names = list(api_names)
        self.timeout = timeout

    def run(self):
        import time

        results = {}
        test_isbn = "9780134685991"
        for api_name in self.api_names:
            try:
                target = create_target_from_config(
                    {"name": api_name, "type": "api", "selected": True, "timeout": self.timeout}
                )
                start_time = time.time()
                result = target.lookup(test_isbn)
                response_time = time.time() - start_time
                no_data_error = (result.error or "").lower()
                online = bool(result.success or "no records found" in no_data_error or "not found" in no_data_error)
                results[api_name] = {
                    "online": online,
                    "response_time": response_time,
                    "error": None if online else (result.error or "Unknown error"),
                }
            except Exception as e:
                results[api_name] = {"online": False, "error": str(e)}

        self.completed.emit(results)


class APIMonitorTab(QWidget):
    """API health monitoring tab."""

    def __init__(self, compact=False):
        super().__init__()
        self.compact = compact
        self.targets_manager = TargetsManager()
        self.target_aliases = {
            "Harvard LibraryCloud": "Harvard",
        }
        self.api_cards = {}
        self.latest_status = {
            "Library of Congress": None,
            "Harvard": None,
            "OpenLibrary": None,
        }
        self.check_worker = None
        self._setup_ui()
        self._load_targets()
        self._start_auto_check()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(12)

        # Title
        title_label = QLabel("API Health Monitor")
        title_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #c2d07f;"
            if self.compact else
            "font-size: 20px; font-weight: bold; color: #c2d07f;"
        )
        layout.addWidget(title_label)

        if not self.compact:
            subtitle_label = QLabel("Real-time monitoring of API targets and their availability")
            subtitle_label.setStyleSheet("color: #a7a59b; font-size: 12px;")
            layout.addWidget(subtitle_label)

        divider = QFrame()
        divider.setObjectName("SectionDivider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        # Status cards container
        cards_group = QGroupBox("API Status")
        cards_layout = QGridLayout()
        cards_layout.setSpacing(15)

        # Create cards for known APIs
        self.api_cards["Library of Congress"] = APIStatusCard("Library of Congress", compact=self.compact)
        self.api_cards["Harvard"] = APIStatusCard("Harvard LibraryCloud", compact=self.compact)
        self.api_cards["OpenLibrary"] = APIStatusCard("OpenLibrary", compact=self.compact)

        cards_layout.addWidget(self.api_cards["Library of Congress"], 0, 0)
        cards_layout.addWidget(self.api_cards["Harvard"], 0, 1)
        cards_layout.addWidget(self.api_cards["OpenLibrary"], 0, 2)

        cards_group.setLayout(cards_layout)
        layout.addWidget(cards_group)

        # Control buttons
        control_group = QGroupBox("Controls")
        control_layout = QHBoxLayout()

        self.check_now_button = QPushButton("Check Now")
        self.check_now_button.setObjectName("PrimaryButton")
        self.check_now_button.clicked.connect(self._check_all_apis)
        self.check_now_button.setToolTip("Immediately check all enabled APIs")

        self.auto_check_label = QLabel("Auto-check: Every 30 seconds")
        self.auto_check_label.setStyleSheet("color: #a7a59b; font-size: 11px; font-style: italic;")

        control_layout.addWidget(self.check_now_button)
        control_layout.addWidget(self.auto_check_label)
        control_layout.addStretch()

        control_group.setLayout(control_layout)
        layout.addWidget(control_group)

        # Status summary
        self.summary_label = QLabel("Status: Not checked")
        self.summary_label.setStyleSheet(
            "font-size: 11px; color: #a7a59b; margin-top: 10px; "
            "padding: 6px 10px; border: 1px solid #2d2e2b; border-radius: 6px; background: #1f201d;"
        )
        layout.addWidget(self.summary_label)

        if not self.compact:
            layout.addStretch()
        self.setLayout(layout)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    @staticmethod
    def _api_key_from_name(name: str):
        normalized = (name or "").strip().lower()
        if "library of congress" in normalized or normalized == "loc":
            return "Library of Congress"
        if "harvard" in normalized:
            return "Harvard"
        if "openlibrary" in normalized or "open library" in normalized:
            return "OpenLibrary"
        return None

    def _load_targets(self):
        """Load target configuration and update API cards."""
        try:
            for card in self.api_cards.values():
                card.set_enabled(False)
                card.set_rank(None)

            all_targets = self.targets_manager.get_all_targets()
            api_targets = []
            for target in all_targets:
                target_type = (target.target_type or "").strip().lower()
                if "z" in target_type:
                    continue
                api_targets.append(target)

            for target in api_targets:
                key = self._api_key_from_name(target.name)
                if key in self.api_cards:
                    self.api_cards[key].set_enabled(bool(target.selected))
                    self.api_cards[key].set_rank(target.rank)
        except Exception as e:
            print(f"API Monitor: Failed to load targets: {e}")

    def _start_auto_check(self):
        """Start automatic API checking."""
        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self._check_all_apis)
        self.check_timer.start(30000 if not self.compact else 45000)

        # Do initial check after 2 seconds
        QTimer.singleShot(2000, self._check_all_apis)

    def _check_all_apis(self):
        """Check the health of all enabled APIs."""
        if self.check_worker and self.check_worker.isRunning():
            return

        self._load_targets()  # Refresh enabled status

        enabled_apis = []
        for name, card in self.api_cards.items():
            if card.enabled:
                enabled_apis.append(name)
            else:
                self.latest_status[name] = None

        self.check_now_button.setEnabled(False)
        self.check_now_button.setText("Checking...")
        if not enabled_apis:
            self._render_summary()
            self.check_now_button.setEnabled(True)
            self.check_now_button.setText("Check Now")
            return

        self.check_worker = APICheckWorker(enabled_apis, timeout=3 if self.compact else 5)
        self.check_worker.completed.connect(self._on_check_completed)
        self.check_worker.start()

    def _on_check_completed(self, results):
        for name, result in results.items():
            card = self.api_cards.get(name)
            if card is None:
                continue
            card.update_status(
                online=result["online"],
                response_time=result.get("response_time"),
                error=result.get("error")
            )
            self.latest_status[name] = result["online"]

        self._render_summary()
        self.check_now_button.setEnabled(True)
        self.check_now_button.setText("Check Now")

    def _render_summary(self):
        online_count = 0
        offline_count = 0
        disabled_count = 0
        for name, card in self.api_cards.items():
            if not card.enabled:
                disabled_count += 1
                continue
            state = self.latest_status.get(name)
            if state:
                online_count += 1
            else:
                offline_count += 1

        # Update summary
        total_enabled = online_count + offline_count
        if total_enabled == 0:
            self.summary_label.setText("Status: All APIs are disabled")
        else:
            self.summary_label.setText(
                f"Status: {online_count}/{total_enabled} APIs online, "
                f"{disabled_count} disabled"
            )

    def showEvent(self, event):
        """Refresh when tab is shown."""
        super().showEvent(event)
        self._load_targets()

    def refresh_status(self):
        """Public method to refresh API status (called by main window)."""
        self._load_targets()

    def status_snapshot(self):
        """Return last known status for quick hover indicators."""
        return dict(self.latest_status)

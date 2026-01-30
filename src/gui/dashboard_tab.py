"""
Module: dashboard_tab.py
Live statistics dashboard with charts and visualizations.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QGridLayout, QFrame
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen, QFont
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from database import DatabaseManager


class StatCard(QFrame):
    """Animated statistic card."""

    def __init__(self, title, value="0", icon="📊", color="#0066cc"):
        super().__init__()
        self.title = title
        self.value = value
        self.icon = icon
        self.color = color
        self._setup_ui()

    def _setup_ui(self):
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: white;
                border-left: 4px solid {self.color};
                border-radius: 8px;
                padding: 15px;
            }}
            QFrame:hover {{
                background-color: #f8f8f8;
            }}
        """)

        layout = QVBoxLayout()

        # Icon and title row
        header_layout = QHBoxLayout()

        icon_label = QLabel(self.icon)
        icon_label.setStyleSheet("font-size: 32px; border: none;")

        title_label = QLabel(self.title)
        title_label.setStyleSheet("font-size: 12px; color: #666666; font-weight: bold; border: none;")

        header_layout.addWidget(icon_label)
        header_layout.addStretch()
        header_layout.addWidget(title_label)

        layout.addLayout(header_layout)

        # Value
        self.value_label = QLabel(self.value)
        self.value_label.setStyleSheet(f"font-size: 36px; font-weight: bold; color: {self.color}; border: none;")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.value_label)

        self.setLayout(layout)

    def update_value(self, new_value):
        """Update the displayed value."""
        self.value = str(new_value)
        self.value_label.setText(self.value)


class SimpleBarChart(QWidget):
    """Simple bar chart widget."""

    def __init__(self, title="Chart", max_bars=5):
        super().__init__()
        self.title = title
        self.data = {}  # {label: value}
        self.max_bars = max_bars
        self.setMinimumHeight(200)

    def set_data(self, data_dict):
        """Set chart data. data_dict = {label: value}"""
        # Keep only top max_bars
        sorted_items = sorted(data_dict.items(), key=lambda x: x[1], reverse=True)
        self.data = dict(sorted_items[:self.max_bars])
        self.update()

    def paintEvent(self, event):
        """Draw the bar chart."""
        if not self.data:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Dimensions
        width = self.width()
        height = self.height()
        margin = 40
        chart_height = height - margin * 2

        # Calculate bar width
        num_bars = len(self.data)
        bar_spacing = 15
        available_width = width - margin * 2 - (num_bars - 1) * bar_spacing
        bar_width = available_width // num_bars if num_bars > 0 else 0

        # Find max value for scaling
        max_value = max(self.data.values()) if self.data else 1

        # Colors
        colors = [
            QColor("#0066cc"),
            QColor("#00cc66"),
            QColor("#ff9900"),
            QColor("#cc00cc"),
            QColor("#00cccc")
        ]

        # Draw title
        painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        painter.drawText(10, 20, self.title)

        # Draw bars
        x = margin
        for i, (label, value) in enumerate(self.data.items()):
            # Calculate bar height
            bar_height = int((value / max_value) * chart_height) if max_value > 0 else 0

            # Draw bar
            color = colors[i % len(colors)]
            painter.setBrush(color)
            painter.setPen(QPen(color.darker(), 1))

            bar_y = height - margin - bar_height
            painter.drawRect(x, bar_y, bar_width, bar_height)

            # Draw value on top
            painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            painter.drawText(x, bar_y - 5, bar_width, 20, Qt.AlignmentFlag.AlignCenter, str(value))

            # Draw label at bottom
            painter.setFont(QFont("Arial", 8))
            label_text = label[:15] + "..." if len(label) > 15 else label
            painter.drawText(x, height - margin + 5, bar_width, 30,
                           Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, label_text)

            x += bar_width + bar_spacing


class DashboardTab(QWidget):
    """Live dashboard with statistics and charts."""

    def __init__(self):
        super().__init__()
        self.db = None
        self._setup_ui()
        self._init_database()
        self._start_auto_refresh()

    def _setup_ui(self):
        layout = QVBoxLayout()

        # Title
        title_label = QLabel("📊 Live Dashboard")
        title_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #0066cc;")
        layout.addWidget(title_label)

        subtitle_label = QLabel("Real-time statistics and performance metrics")
        subtitle_label.setStyleSheet("font-size: 12px; color: #666666; margin-bottom: 10px;")
        layout.addWidget(subtitle_label)

        # Stat Cards
        cards_layout = QGridLayout()

        self.total_card = StatCard("Total Records", "0", "📚", "#0066cc")
        self.found_card = StatCard("LCCNs Found", "0", "✅", "#00cc66")
        self.failed_card = StatCard("Failed", "0", "❌", "#ff3333")
        self.cached_card = StatCard("Cache Hits", "0", "⚡", "#ff9900")

        cards_layout.addWidget(self.total_card, 0, 0)
        cards_layout.addWidget(self.found_card, 0, 1)
        cards_layout.addWidget(self.failed_card, 0, 2)
        cards_layout.addWidget(self.cached_card, 0, 3)

        layout.addLayout(cards_layout)

        # Success Rate Card
        success_group = QGroupBox("Success Rate")
        success_layout = QVBoxLayout()

        self.success_rate_label = QLabel("0%")
        self.success_rate_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.success_rate_label.setStyleSheet("font-size: 48px; font-weight: bold; color: #00cc66;")
        success_layout.addWidget(self.success_rate_label)

        self.success_subtitle = QLabel("Overall harvest success rate")
        self.success_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.success_subtitle.setStyleSheet("font-size: 11px; color: #666666;")
        success_layout.addWidget(self.success_subtitle)

        success_group.setLayout(success_layout)
        layout.addWidget(success_group)

        # Charts
        charts_layout = QHBoxLayout()

        # Source Breakdown Chart
        source_group = QGroupBox("Sources Breakdown")
        source_layout = QVBoxLayout()

        self.source_chart = SimpleBarChart("Records by Source", max_bars=5)
        source_layout.addWidget(self.source_chart)

        source_group.setLayout(source_layout)
        charts_layout.addWidget(source_group)

        # Classification Chart
        class_group = QGroupBox("Top Classifications")
        class_layout = QVBoxLayout()

        self.class_chart = SimpleBarChart("Top 5 Classifications", max_bars=5)
        class_layout.addWidget(self.class_chart)

        class_group.setLayout(class_layout)
        charts_layout.addWidget(class_group)

        layout.addLayout(charts_layout)

        # Last Updated
        self.last_updated_label = QLabel("Last updated: Never")
        self.last_updated_label.setStyleSheet("font-size: 10px; color: #999999; margin-top: 10px;")
        self.last_updated_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.last_updated_label)

        layout.addStretch()
        self.setLayout(layout)

    def _init_database(self):
        """Initialize database connection."""
        try:
            self.db = DatabaseManager()
            self.db.init_db()
            self.refresh_data()
        except Exception as e:
            print(f"Dashboard: Failed to initialize database: {e}")

    def _start_auto_refresh(self):
        """Start auto-refresh timer."""
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_data)
        self.refresh_timer.start(5000)  # Refresh every 5 seconds

    def refresh_data(self):
        """Refresh all dashboard data."""
        if not self.db:
            return

        try:
            with self.db.connect() as conn:
                # Get total records
                total = conn.execute("SELECT COUNT(*) FROM main").fetchone()[0]
                self.total_card.update_value(total)

                # Get records with LCCN
                found = conn.execute("SELECT COUNT(*) FROM main WHERE lccn IS NOT NULL").fetchone()[0]
                self.found_card.update_value(found)

                # Get failed attempts
                failed = conn.execute("SELECT COUNT(*) FROM attempted").fetchone()[0]
                self.failed_card.update_value(failed)

                # Calculate cached (approximate - records older than 1 day)
                cached = conn.execute(
                    "SELECT COUNT(*) FROM main WHERE date_added < date('now', '-1 day')"
                ).fetchone()[0]
                self.cached_card.update_value(cached)

                # Calculate success rate
                if total > 0:
                    success_rate = (found / total) * 100
                    self.success_rate_label.setText(f"{success_rate:.1f}%")

                    # Color based on rate
                    if success_rate >= 70:
                        color = "#00cc66"
                    elif success_rate >= 40:
                        color = "#ff9900"
                    else:
                        color = "#ff3333"
                    self.success_rate_label.setStyleSheet(
                        f"font-size: 48px; font-weight: bold; color: {color};"
                    )

                # Get source breakdown
                source_data = {}
                rows = conn.execute(
                    "SELECT source, COUNT(*) as count FROM main WHERE source IS NOT NULL GROUP BY source ORDER BY count DESC LIMIT 5"
                ).fetchall()
                for row in rows:
                    source_data[row[0]] = row[1]
                self.source_chart.set_data(source_data)

                # Get classification breakdown
                class_data = {}
                rows = conn.execute(
                    "SELECT classification, COUNT(*) as count FROM main WHERE classification IS NOT NULL GROUP BY classification ORDER BY count DESC LIMIT 5"
                ).fetchall()
                for row in rows:
                    class_data[row[0]] = row[1]
                self.class_chart.set_data(class_data)

                # Update timestamp
                from datetime import datetime
                self.last_updated_label.setText(
                    f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )

        except Exception as e:
            print(f"Dashboard: Failed to refresh data: {e}")

    def showEvent(self, event):
        """Refresh when tab is shown."""
        super().showEvent(event)
        self.refresh_data()

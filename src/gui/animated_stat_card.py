"""
Module: animated_stat_card.py
Animated statistic card with smooth number transitions.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QPainter, QColor, QPen


class AnimatedStatCard(QFrame):
    """A card that displays an animated statistic."""

    def __init__(self, title, color="#3498db", parent=None):
        super().__init__(parent)
        self.title = title
        self.color = color
        self._current_value = 0
        self._display_value = 0
        self.animation = None
        self._setup_ui()

    def _setup_ui(self):
        """Setup the card UI."""
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {self.color},
                    stop:1 {self._darken_color(self.color)}
                );
                border-radius: 8px;
                padding: 15px;
            }}
        """)

        layout = QVBoxLayout()
        layout.setSpacing(5)

        # Title
        self.title_label = QLabel(self.title)
        self.title_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 13px;
                font-weight: bold;
                font-family: Arial, Helvetica;
                background: transparent;
            }
        """)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

        # Value
        self.value_label = QLabel("0")
        self.value_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 38px;
                font-weight: bold;
                font-family: Arial, Helvetica;
                background: transparent;
            }
        """)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_label.setWordWrap(False)
        self.value_label.setScaledContents(False)
        layout.addWidget(self.value_label)

        # Subtitle (percentage or rate)
        self.subtitle_label = QLabel("")
        self.subtitle_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 14px;
                font-weight: 500;
                font-family: Arial, Helvetica;
                background: transparent;
            }
        """)
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.subtitle_label)

        layout.addStretch()
        self.setLayout(layout)
        self.setMinimumHeight(140)
        self.setMinimumWidth(180)

    def _darken_color(self, hex_color):
        """Darken a hex color by 20%."""
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        rgb = tuple(max(0, int(c * 0.8)) for c in rgb)
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    @pyqtProperty(float)
    def displayValue(self):
        """Get the current display value."""
        return self._display_value

    @displayValue.setter
    def displayValue(self, value):
        """Set the display value and update the label."""
        self._display_value = value
        # Convert to plain string to avoid Unicode issues
        int_value = int(value)
        # Format with commas for readability
        if int_value >= 1000:
            formatted_value = f"{int_value:,}"
        else:
            formatted_value = str(int_value)
        self.value_label.setText(formatted_value)

    def set_value(self, value, animate=True):
        """Set the value with optional animation."""
        if not animate or self._current_value == value:
            self._current_value = value
            self.displayValue = value
            return

        # Stop any running animation
        if self.animation:
            self.animation.stop()

        # Create animation
        self.animation = QPropertyAnimation(self, b"displayValue")
        self.animation.setDuration(500)  # 500ms animation
        self.animation.setStartValue(self._current_value)
        self.animation.setEndValue(value)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.start()

        self._current_value = value

    def set_subtitle(self, text):
        """Set the subtitle text."""
        self.subtitle_label.setText(text)

    def pulse(self):
        """Create a pulse effect (for milestone notifications)."""
        # Could add a brief color pulse animation here
        pass


class CircularProgress(QWidget):
    """Circular progress indicator."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self._max_value = 100
        self.setMinimumSize(150, 150)

    def set_value(self, value):
        """Set the progress value."""
        self._value = value
        self.update()

    def set_max(self, max_value):
        """Set the maximum value."""
        self._max_value = max_value

    def paintEvent(self, event):
        """Paint the circular progress."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Get dimensions
        width = self.width()
        height = self.height()
        size = min(width, height)
        rect_size = size - 20

        # Center rectangle
        rect = (
            (width - rect_size) // 2,
            (height - rect_size) // 2,
            rect_size,
            rect_size
        )

        # Background circle
        painter.setPen(QPen(QColor(230, 230, 230), 12))
        painter.drawEllipse(*rect)

        # Progress arc
        if self._max_value > 0:
            percent = self._value / self._max_value
            angle = int(percent * 360 * 16)  # Qt uses 1/16th degree

            # Color based on progress
            if percent < 0.5:
                color = QColor(52, 152, 219)  # Blue
            elif percent < 0.75:
                color = QColor(46, 204, 113)  # Green
            else:
                color = QColor(155, 89, 182)  # Purple

            painter.setPen(QPen(color, 12, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(*rect, 90 * 16, -angle)

        # Percentage text
        if self._max_value > 0:
            percent = int((self._value / self._max_value) * 100)
            painter.setPen(QColor(50, 50, 50))
            painter.setFont(painter.font())
            font = painter.font()
            font.setPointSize(24)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(0, 0, width, height, Qt.AlignmentFlag.AlignCenter, f"{percent}%")

"""Reusable dashboard widgets and standalone formatting helpers.

These pieces are kept separate from ``dashboard.py`` so the tab class can
focus on page-level state changes while the visual building blocks remain easy
to scan and reuse independently.

Contents:
- File utilities: ``write_csv_copy``, ``safe_filename``
- Text helpers: ``truncate_text``, ``normalize_recent_detail``,
  ``problems_button_label``
- Widgets: ``DashboardCard``, ``RecentResultsPanel``, ``ProfileSwitchCombo``

Usage notes:
- ``DashboardCard`` relies on the ``"Card"``, ``"CardTitle"``, ``"CardValue"``, and
  ``"CardHelper"`` QSS classes defined in ``styles.py``.
- ``RecentResultsPanel`` sets a fixed height after each data update via
  ``_fit_table_height`` so the enclosing scroll area always sees the correct size.
- ``ProfileSwitchCombo`` subclasses ``QComboBox`` solely to paint a custom chevron;
  all other combo behaviour is inherited unchanged.
"""

from __future__ import annotations

import csv
import re

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .icons import get_pixmap


def write_csv_copy(tsv_path: str, csv_path: str) -> None:
    """Convert a TSV file to a UTF-8 CSV (with BOM) for spreadsheet apps.

    The BOM (``utf-8-sig``) ensures Excel opens the file with correct encoding
    on Windows without a manual import wizard.

    Args:
        tsv_path: Absolute path to the source TSV file.
        csv_path: Absolute path to write the converted CSV file.
    """
    with open(tsv_path, newline="", encoding="utf-8") as source:
        rows = csv.reader(source, delimiter="\t")
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as target:
            writer = csv.writer(target)
            writer.writerows(rows)


def safe_filename(value: str) -> str:
    """Strip characters that are awkward or invalid in file names.

    Replaces each character in ``\\/:*?"<>|`` and spaces with underscores, then
    trims leading/trailing underscores.  Returns ``"default"`` for empty input.

    Args:
        value: Raw string to sanitise (e.g. a profile name).

    Returns:
        File-system-safe string, never empty.
    """
    cleaned = "".join("_" if c in '\\/:*?"<>| ' else c for c in (value or "").strip())
    cleaned = cleaned.strip("_")
    return cleaned or "default"


def problems_button_label(
    profile_name: str | None,
    file_name: str | None = None,
    include_profile: bool = False,
) -> str:
    """Return the label used for the target-problems export button.

    The unused parameters are intentionally kept so callers can evolve without
    needing another signature change in the middle of the GUI code.
    """
    _ = profile_name, file_name, include_profile
    return "Open targets problems"


def truncate_text(text: str, limit: int = 110) -> str:
    """Trim *text* to *limit* characters, appending ``"..."`` when truncated.

    Args:
        text: Input string (may be ``None`` or non-string; coerced via ``str``).
        limit: Maximum number of characters before truncation (default 110).

    Returns:
        The original string if it fits, or a truncated string ending with ``"..."``.
    """
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def normalize_recent_detail(text: str) -> str:
    """Collapse duplicate source labels in the recent-results table.

    Splits on common separators (``+``, ``,``, ``;``, ``|``), normalises the
    known ``UCB`` → ``UBC`` alias, deduplicates, and rejoins with " + ".
    Returns "-" for empty or whitespace-only input.
    """
    parts: list[str] = []
    for piece in re.split(r"[+,;|]", str(text or "")):
        cleaned = piece.strip()
        # Normalise known alias: "UCB" is a common typo for "UBC" (University of British Columbia).
        if cleaned.upper() == "UCB":
            cleaned = "UBC"
        elif cleaned.upper() == "UBC":
            cleaned = "UBC"
        if cleaned and cleaned not in parts:
            parts.append(cleaned)
    return " + ".join(parts) if parts else (str(text or "").strip() or "-")


class DashboardCard(QFrame):
    """A single KPI metric card with an icon, title label, large numeric value, and helper text.

    The card follows the ``Card`` QSS class so it adopts the current theme's
    surface background, border, and hover highlight automatically.
    """

    def __init__(self, title, icon_svg, accent_color="#8aadf4"):
        """Args:
            title: Short uppercase label shown above the numeric value.
            icon_svg: SVG string constant from ``icons.py``.
            accent_color: Hex color used to tint the icon.
        """
        super().__init__()
        # The "Card" class triggers the QSS card styling (rounded corners, border, etc.)
        self.setProperty("class", "Card")
        self.setMinimumWidth(220)
        self._setup_ui(title, icon_svg, accent_color)

    def _setup_ui(self, title, icon_svg, accent_color):
        """Build the card layout: header row (title left, icon right), value, helper text."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(5)

        header_layout = QHBoxLayout()
        lbl_title = QLabel(title)
        # "CardTitle" QSS class applies uppercase, small-caps styling.
        lbl_title.setProperty("class", "CardTitle")

        icon_lbl = QLabel()
        # Render the SVG icon as a pixmap tinted with the accent colour, 24×24 px.
        icon_lbl.setPixmap(get_pixmap(icon_svg, accent_color, 24))

        header_layout.addWidget(lbl_title)
        header_layout.addStretch()
        header_layout.addWidget(icon_lbl)

        layout.addLayout(header_layout)

        self.lbl_value = QLabel("0")
        self.lbl_value.setProperty("class", "CardValue")
        layout.addWidget(self.lbl_value)

        self.lbl_helper = QLabel("Total records")
        self.lbl_helper.setProperty("class", "CardHelper")
        layout.addWidget(self.lbl_helper)

    def set_data(self, value, helper_text=""):
        """Update the displayed numeric value and optional helper text.

        Args:
            value: The KPI count to display (converted to string automatically).
            helper_text: Secondary description shown below the number.  Empty
                         string leaves the previous helper text unchanged.
        """
        self.lbl_value.setText(str(value))
        if helper_text:
            self.lbl_helper.setText(helper_text)


class RecentResultsPanel(QFrame):
    """Compact read-only table showing up to 10 of the most recent harvest results.

    Each row displays an ISBN, a colour-coded status label (green for success,
    red otherwise), and a truncated detail string.  The table disables scroll bars
    and interactive selection to keep it purely informational.
    """

    def __init__(self):
        super().__init__()
        # "Card" class applies themed border/background via QSS
        self.setProperty("class", "Card")
        self._setup_ui()

    def _setup_ui(self):
        """Build the panel: title label above a read-only, scroll-bar-free table."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        header = QLabel("RECENT RESULTS")
        header.setProperty("class", "CardTitle")
        layout.addWidget(header)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["ISBN", "Status", "Detail"])
        # ISBN and Status columns auto-size; Detail column stretches to fill remaining width.
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        # NoFocus prevents a blue focus ring from appearing when the user clicks the table.
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # Disable selection to make the table purely informational (no row highlighting).
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        # Hide both scroll bars; height is managed manually by _fit_table_height.
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setWordWrap(False)
        # Transparent background so the surrounding Card frame shows through.
        self.table.setStyleSheet("background: transparent; border: none;")

        layout.addWidget(self.table)

    def update_data(self, records):
        """Replace the table contents with the supplied records list.

        Args:
            records: Sequence of dicts with keys ``isbn``, ``status``, and
                     ``detail``.  Pass an empty list to clear the table.
        """
        self.table.setRowCount(0)
        for row_idx, record in enumerate(records):
            self.table.insertRow(row_idx)

            self.table.setItem(row_idx, 0, QTableWidgetItem(record["isbn"]))

            status = record["status"]
            item_status = QTableWidgetItem(status)
            # Colour-code status: green for success outcomes, red for everything else.
            if status in {"Successful", "Found", "Linked ISBN"}:
                item_status.setForeground(QColor("#2e7d32"))
            else:
                item_status.setForeground(QColor("#c62828"))
            self.table.setItem(row_idx, 1, item_status)

            detail_text = normalize_recent_detail(record.get("detail") or "-")
            # Truncate long details in the cell but show the full text in a tooltip.
            item_detail = QTableWidgetItem(truncate_text(detail_text, 90))
            item_detail.setToolTip(detail_text)
            self.table.setItem(row_idx, 2, item_detail)
        self._fit_table_height()

    def _fit_table_height(self):
        """Resize the table widget to exactly fit all visible rows without a scroll bar.

        Always reserves height for at least 10 rows so the panel does not jump in
        size when transitioning between an empty and a partially-filled state.
        """
        header_height = self.table.horizontalHeader().height() or 34
        row_height = self.table.verticalHeader().defaultSectionSize() or 26
        visible_rows = max(10, self.table.rowCount())
        self.table.setFixedHeight(header_height + (row_height * visible_rows) + 8)


class ProfileSwitchCombo(QComboBox):
    """Dashboard profile switcher that paints its own chevron arrow.

    The native QComboBox drop-down arrow can disappear under certain QSS rules.
    This subclass overlays a manually-drawn chevron in the ``paintEvent`` so the
    affordance is always visible regardless of the active stylesheet.
    """

    def paintEvent(self, event):
        """Draw the base combo box then overlay a custom chevron arrow."""
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Draw the chevron in a light contrasting colour near the right edge.
        painter.setPen(QPen(QColor("#e6eaf6"), 2))
        cx = self.width() - 21   # horizontal centre of the chevron, inset from the right
        cy = self.height() // 2 + 1
        size = 5                  # half-width of the downward-pointing chevron
        painter.drawLine(cx - size, cy - 2, cx, cy + 3)
        painter.drawLine(cx, cy + 3, cx + size, cy - 2)
        painter.end()

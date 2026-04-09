"""Dialog for inspecting and managing the ``linked_isbns`` database table.

``LinkedIsbnDialog`` exposes three operations through a single scrollable form:

1. **Query** — look up the canonical (lowest) ISBN for any ISBN and list all
   ISBNs linked under it.
2. **Link** — store a mapping that marks one ISBN as a variant of another
   without moving any existing ``main`` or ``attempted`` rows.
3. **Rewrite & Merge** — migrate all ``main`` and ``attempted`` rows from an
   "other" ISBN onto the canonical "lowest" ISBN, merging call numbers and
   fail counts, then record the link.  This is a destructive operation and
   cannot be undone.

The content is placed inside a ``QScrollArea`` so the form remains usable on
small screens.  The Close button lives outside the scroll area so it is always
visible.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QTextEdit, QScrollArea, QWidget, QFormLayout
)
from PyQt6.QtCore import Qt

from database import DatabaseManager


class LinkedIsbnDialog(QDialog):
    """Modal dialog for querying, linking, and merging linked ISBN records.

    All three operations delegate to ``DatabaseManager`` methods so no raw SQL
    is issued from this class.  Feedback (success or error) is displayed in the
    ``status_label`` at the bottom of the form.
    """

    def __init__(self, parent=None, db: DatabaseManager | None = None):
        """Initialise the dialog and ensure the database schema exists.

        Args:
            parent: Optional parent widget for modal positioning.
            db: An initialised ``DatabaseManager`` instance; a new one is
                created if not supplied.
        """
        super().__init__(parent)
        self.setWindowTitle("Linked ISBNs")
        self.setMinimumWidth(520)
        self.db = db or DatabaseManager()
        self.db.init_db()   # ensure the linked_isbns table exists before any query
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _setup_ui(self):
        """Build the dialog layout with three sections inside a QScrollArea.

        Layout hierarchy:
            QVBoxLayout (outer)
            ├── QScrollArea (scroll)  — contains the three form sections
            │   └── QWidget (content)
            │       └── QVBoxLayout (root)
            │           ├── Section header: QUERY
            │           ├── Query input row + result text area
            │           ├── Section header: LINK TWO ISBNs
            │           ├── Link form (QFormLayout) + Save Link button
            │           ├── Section header: REWRITE TO LOWEST ISBN
            │           ├── Rewrite form (QFormLayout) + Rewrite & Merge button
            │           └── status_label
            └── Close button (outside scroll, always visible)

        The Close button is placed outside the scroll area so it remains
        accessible even when the content is taller than the dialog window.
        """
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setSpacing(12)
        root.setContentsMargins(24, 20, 24, 20)

        sub = QLabel(
            "Query which ISBNs are linked together, manually link two ISBNs, "
            "or consolidate existing rows under the lowest ISBN."
        )
        sub.setProperty("class", "HelperText")
        sub.setWordWrap(True)
        root.addWidget(sub)

        # ── Section 1: Query ──────────────────────────────────────────
        root.addWidget(self._section_header("QUERY"))

        q_row = QHBoxLayout()
        q_row.setSpacing(8)
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Enter any ISBN…")
        self.query_input.setMinimumHeight(38)
        self.query_input.returnPressed.connect(self._run_query)
        q_row.addWidget(self.query_input, stretch=1)

        btn_query = QPushButton("Look Up")
        btn_query.setProperty("class", "PrimaryButton")
        btn_query.setMinimumHeight(38)
        btn_query.setMinimumWidth(100)
        btn_query.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_query.clicked.connect(self._run_query)
        q_row.addWidget(btn_query)
        root.addLayout(q_row)

        self.query_result = QTextEdit()
        self.query_result.setReadOnly(True)
        self.query_result.setFixedHeight(100)
        self.query_result.setPlaceholderText("Results appear here…")
        self.query_result.setProperty("class", "TerminalViewport")
        root.addWidget(self.query_result)

        # ── Section 2: Link ISBNs ─────────────────────────────────────
        root.addWidget(self._section_header("LINK TWO ISBNs"))

        helper_link = QLabel(
            "Mark <b>Other ISBN</b> as a variant of <b>Lowest ISBN</b>. "
            "No existing rows are moved — only the mapping is stored."
        )
        helper_link.setProperty("class", "HelperText")
        helper_link.setWordWrap(True)
        root.addWidget(helper_link)

        link_form = QFormLayout()
        link_form.setSpacing(8)
        link_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        link_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.link_lowest = QLineEdit()
        self.link_lowest.setPlaceholderText("Canonical / lowest ISBN")
        self.link_lowest.setMinimumHeight(36)
        link_form.addRow("Lowest ISBN:", self.link_lowest)

        self.link_other = QLineEdit()
        self.link_other.setPlaceholderText("Variant / higher ISBN")
        self.link_other.setMinimumHeight(36)
        link_form.addRow("Other ISBN:", self.link_other)
        root.addLayout(link_form)

        btn_link_row = QHBoxLayout()
        btn_link_row.addStretch()
        btn_link = QPushButton("Save Link")
        btn_link.setProperty("class", "SecondaryButton")
        btn_link.setMinimumHeight(38)
        btn_link.setMinimumWidth(130)
        btn_link.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_link.clicked.connect(self._run_link)
        btn_link_row.addWidget(btn_link)
        root.addLayout(btn_link_row)

        # ── Section 3: Rewrite to Lowest ─────────────────────────────
        root.addWidget(self._section_header("REWRITE TO LOWEST ISBN"))

        helper_rw = QLabel(
            "Move all <b>main</b> and <b>attempted</b> rows from Other ISBN onto "
            "Lowest ISBN, merging call numbers and fail counts, then store the link."
        )
        helper_rw.setProperty("class", "HelperText")
        helper_rw.setWordWrap(True)
        root.addWidget(helper_rw)

        rw_form = QFormLayout()
        rw_form.setSpacing(8)
        rw_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        rw_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.rw_lowest = QLineEdit()
        self.rw_lowest.setPlaceholderText("Keep this ISBN")
        self.rw_lowest.setMinimumHeight(36)
        rw_form.addRow("Lowest ISBN:", self.rw_lowest)

        self.rw_other = QLineEdit()
        self.rw_other.setPlaceholderText("Merge this ISBN into lowest")
        self.rw_other.setMinimumHeight(36)
        rw_form.addRow("Other ISBN:", self.rw_other)
        root.addLayout(rw_form)

        btn_rw_row = QHBoxLayout()
        btn_rw_row.addStretch()
        btn_rewrite = QPushButton("Rewrite && Merge")
        btn_rewrite.setProperty("class", "DangerButton")
        btn_rewrite.setMinimumHeight(38)
        btn_rewrite.setMinimumWidth(160)
        btn_rewrite.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_rewrite.setToolTip("Moves rows in the database — this cannot be undone.")
        btn_rewrite.clicked.connect(self._run_rewrite)
        btn_rw_row.addWidget(btn_rewrite)
        root.addLayout(btn_rw_row)

        # ── Status ────────────────────────────────────────────────────
        self.status_label = QLabel("")
        self.status_label.setProperty("class", "HelperText")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        root.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

        # Close button outside scroll
        bottom = QHBoxLayout()
        bottom.setContentsMargins(24, 8, 24, 16)
        bottom.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setProperty("class", "SecondaryButton")
        close_btn.setMinimumHeight(38)
        close_btn.setMinimumWidth(100)
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)
        bottom.addStretch()
        outer.addLayout(bottom)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _section_header(self, title: str) -> QWidget:
        """Build a bold section label above a horizontal rule.

        Returns a container widget that combines a ``QLabel`` (styled with the
        ``CardTitle`` class) and a ``QFrame`` horizontal rule, so each section
        within the form has a visually distinct heading.

        Args:
            title: Uppercase section name (e.g. ``"QUERY"``).

        Returns:
            A ``QWidget`` containing the label and the divider line.
        """
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(4)

        lbl = QLabel(title)
        # "CardTitle" applies bold/muted styling from the application stylesheet.
        lbl.setProperty("class", "CardTitle")
        layout.addWidget(lbl)

        # Thin horizontal rule separates the heading from the form fields below.
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        layout.addWidget(line)

        return container

    def _set_status(self, msg: str, error: bool = False):
        """Update the status label text and colour.

        Args:
            msg: Message to display.
            error: If ``True``, the label is coloured red; otherwise green.
        """
        # Red (#ef4444) for errors, green (#22c55e) for success messages.
        color = "#ef4444" if error else "#22c55e"
        self.status_label.setText(msg)
        self.status_label.setStyleSheet(f"color: {color};")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _run_query(self):
        """Look up the canonical ISBN and all linked variants for the entered ISBN.

        Calls ``db.get_lowest_isbn`` to find the canonical form and
        ``db.get_linked_isbns`` to list all variants.  Results are displayed
        in the read-only ``query_result`` text area.
        """
        isbn = self.query_input.text().strip()
        if not isbn:
            self._set_status("Please enter an ISBN to look up.", error=True)
            return
        try:
            lowest = self.db.get_lowest_isbn(isbn)
            linked = self.db.get_linked_isbns(isbn)

            lines = []
            if lowest != isbn:
                lines.append(f"Canonical lowest ISBN for '{isbn}':  {lowest}")
            else:
                lines.append(f"'{isbn}' is already the canonical lowest (or unlinked).")

            if linked:
                lines.append(f"\nISBNs linked under '{isbn}':")
                for other in linked:
                    lines.append(f"  • {other}")
            else:
                lines.append(f"\nNo other ISBNs are linked under '{isbn}'.")

            self.query_result.setPlainText("\n".join(lines))
            self._set_status("Query complete.")
        except Exception as exc:
            self.query_result.setPlainText(f"Error: {exc}")
            self._set_status(str(exc), error=True)

    def _run_link(self):
        """Store a mapping that marks *other* as a variant of *lowest*.

        Calls ``db.upsert_linked_isbn`` which inserts or replaces the row in
        the ``linked_isbns`` table.  No existing ``main`` or ``attempted`` rows
        are touched — only the mapping is recorded.
        """
        lowest = self.link_lowest.text().strip()
        other = self.link_other.text().strip()
        if not lowest or not other:
            self._set_status("Both Lowest ISBN and Other ISBN are required.", error=True)
            return
        if lowest == other:
            self._set_status("Lowest and Other ISBN must be different.", error=True)
            return
        try:
            self.db.upsert_linked_isbn(lowest_isbn=lowest, other_isbn=other)
            self.link_lowest.clear()
            self.link_other.clear()
            self._set_status(f"Linked: '{other}'  →  '{lowest}'")
        except Exception as exc:
            self._set_status(str(exc), error=True)

    def _run_rewrite(self):
        """Merge all database rows from *other* ISBN into *lowest* ISBN.

        Calls ``db.rewrite_to_lowest_isbn`` which migrates ``main`` and
        ``attempted`` rows (merging call numbers and fail counts) then stores
        the link.  This operation modifies existing data and cannot be undone
        from the UI.
        """
        lowest = self.rw_lowest.text().strip()
        other = self.rw_other.text().strip()
        if not lowest or not other:
            self._set_status("Both Lowest ISBN and Other ISBN are required.", error=True)
            return
        if lowest == other:
            self._set_status("Lowest and Other ISBN must be different.", error=True)
            return
        try:
            self.db.rewrite_to_lowest_isbn(lowest_isbn=lowest, other_isbn=other)
            self.rw_lowest.clear()
            self.rw_other.clear()
            self._set_status(f"Rewritten: all rows from '{other}' merged into '{lowest}'.")
        except Exception as exc:
            self._set_status(str(exc), error=True)

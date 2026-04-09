"""Input file selection tab for the ISBN input list.

``InputTab`` provides a drag-and-drop zone, a file-browser button, a text
preview of the first ``PREVIEW_MAX_LINES`` lines of the selected file, and a
summary panel that reports file size, total rows, valid ISBN count, duplicate
count, and invalid count.

This tab is kept deliberately lightweight; ISBN validation is delegated to
``src.utils.isbn_validator.normalize_isbn``.

Module-level constants:
    PREVIEW_MAX_LINES (int): Maximum lines shown in the text preview (20).
    LARGE_FILE_THRESHOLD_BYTES (int): Files above this size (20 MB) are sampled
        rather than fully scanned to keep the UI responsive.
    INFO_SAMPLE_MAX_LINES (int): Number of lines examined for the stats summary
        when a file exceeds ``LARGE_FILE_THRESHOLD_BYTES`` (200 000).

Note: ``ClickableDropZone`` is also imported directly by ``harvest_tab.py`` as
a drop target for the run-setup card.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QGroupBox,
    QTextEdit, QFrame, QSizePolicy, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent
from pathlib import Path
from itertools import islice
from src.utils.isbn_validator import normalize_isbn

PREVIEW_MAX_LINES = 20
LARGE_FILE_THRESHOLD_BYTES = 20 * 1024 * 1024  # 20 MB
INFO_SAMPLE_MAX_LINES = 200_000


class ClickableDropZone(QFrame):
    """A ``QFrame`` that acts as both a click target and a drag-and-drop landing zone.

    Clicking anywhere inside the frame emits ``clicked`` (typically wired to a
    file-browser dialog).  Dropping a local file onto the frame emits
    ``fileDropped`` with the first valid file path.

    The ``state`` dynamic property (``"ready"``, ``"active"``, ``"success"``)
    drives QSS visual feedback during drag-over and after a successful drop.

    Signals:
        clicked(): Emitted on a left mouse-button press.
        fileDropped(str): Emitted with the absolute path of the dropped file.
    """

    # Emitted on left mouse-button press anywhere inside the frame.
    clicked = pyqtSignal()
    # Emitted with the absolute path of the first valid file when a drop lands.
    fileDropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # "DragZone" QSS class provides the dashed border / background styling.
        self.setProperty("class", "DragZone")
        # Initial state drives the QSS DragZone[state="ready"] selector.
        self.setProperty("state", "ready")

    def mousePressEvent(self, event: QMouseEvent):
        """Emit ``clicked`` on left mouse-button press so the zone acts as a button."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Accept the drag and switch to the ``"active"`` (hover) QSS state.

        Only accepts drags that contain at least one local file URL.
        """
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path:
                    event.acceptProposedAction()
                    self._update_state("active")
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        """Restore the ready appearance when the drag cursor leaves this widget."""
        self._update_state("ready")

    def dropEvent(self, event: QDropEvent):
        """Accept the dropped file and emit ``fileDropped`` with the path.

        Shows a brief "success" state flash (500 ms) then resets to "ready".
        """
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        valid_files = [f for f in files if f]

        if valid_files:
            file_path = valid_files[0]
            self.fileDropped.emit(file_path)

            # Flash "success" state for a brief visual confirmation of the drop.
            self._update_state("success")

            # Reset to "ready" after 500 ms so the zone is reusable immediately.
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(500, lambda: self._update_state("ready"))

            event.acceptProposedAction()
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Invalid File",
                "Please drop a valid file."
            )
            event.ignore()
            self._update_state("ready")
            
    def _update_state(self, state: str):
        """Update the QSS ``state`` dynamic property and force a re-polish.

        Args:
            state: One of ``"ready"``, ``"active"`` (drag hover), or ``"success"``
                   (brief flash after a successful drop).
        """
        self.setProperty("state", state)
        # unpolish/polish forces Qt to re-evaluate DragZone[state="..."] rules.
        self.style().unpolish(self)
        self.style().polish(self)


class InputTab(QWidget):
    """Standalone input file selection tab (used when the tab is shown on its own page).

    Provides a ``ClickableDropZone`` (drag-and-drop + click-to-browse), a read-only
    path display, a plain-text file preview (first ``PREVIEW_MAX_LINES`` lines),
    and a "File Information" summary panel with valid/invalid/duplicate counts.

    The tab scrolls vertically inside a ``QScrollArea`` so it fits small windows.

    Key instance variables:
        input_file (Path | None): ``Path`` object for the currently loaded file,
            or ``None`` when no file is selected.
        advanced_mode (bool): Placeholder for future advanced-mode UI extensions;
            has no effect in the current implementation.

    Signals:
        file_selected(str): Emitted with the absolute file path whenever a file
            is loaded (via browse or drop).
    """

    # Emitted with the absolute path whenever a file is successfully loaded.
    file_selected = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.input_file = None
        self._setup_ui()

    def _setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)

        # Title
        title_label = QLabel("Input File Selection")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title_label)

        # Instructions
        instructions = QLabel(
            "Select a file containing ISBNs to process. The file should be:\n"
            "• Tab-separated values (TSV) format\n"
            "• First column contains ISBN numbers\n"
            "• ISBNs can be 10 or 13 digits, with or without hyphens\n"
            "• Lines starting with # are ignored (comments)"
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Drag & Drop Zone
        self.drop_zone = ClickableDropZone()
        self.drop_zone.setObjectName("DropZone")  # For styling
        self.drop_zone.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)
        self.drop_zone.setMinimumHeight(120)
        self.drop_zone.clicked.connect(self._browse_file)  # Connect click to browse
        self.drop_zone.fileDropped.connect(self._handle_file_drop)  # Connect drop to handler

        drop_layout = QVBoxLayout()
        drop_icon = QLabel("📁")
        drop_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_icon.setStyleSheet("font-size: 48px; border: none; background: transparent;")

        drop_text = QLabel("Drag & Drop ISBN File Here\nor click anywhere to browse")
        drop_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_text.setStyleSheet("font-size: 14px; font-weight: bold; border: none; background: transparent;")

        drop_hint = QLabel("Supports: .tsv, .txt, .csv, and Excel (.xlsx/.xls)")
        drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_hint.setStyleSheet("font-size: 11px; border: none; background: transparent;")

        drop_layout.addWidget(drop_icon)
        drop_layout.addWidget(drop_text)
        drop_layout.addWidget(drop_hint)
        drop_layout.setContentsMargins(16, 16, 16, 16)
        drop_layout.setSpacing(6)

        self.drop_zone.setLayout(drop_layout)
        layout.addWidget(self.drop_zone)

        # File selection group
        file_group = QGroupBox("Select Input File")
        file_layout = QVBoxLayout()

        # File path display and browse button
        path_layout = QHBoxLayout()
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setPlaceholderText("No file selected...")
        self.file_path_edit.setReadOnly(True)

        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self._browse_file)

        path_layout.addWidget(self.file_path_edit)
        path_layout.addWidget(self.browse_button)
        file_layout.addLayout(path_layout)

        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        # File preview
        preview_group = QGroupBox("File Preview")
        preview_layout = QVBoxLayout()

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText("Select a file to preview its contents...")
        self.preview_text.setMaximumHeight(300)

        preview_layout.addWidget(self.preview_text)
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)

        # File info
        info_group = QGroupBox("File Information")
        info_layout = QVBoxLayout()

        self.info_label = QLabel("No file selected")
        self.info_label.setWordWrap(True)
        self.info_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info_layout.addWidget(self.info_label)

        info_group.setLayout(info_layout)
        info_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout.addWidget(info_group)

        layout.addStretch()
        scroll.setWidget(content)
        root_layout.addWidget(scroll)
        self.advanced_mode = False

    def set_advanced_mode(self, enabled):
        """Enable or disable advanced-mode features (no-op for now).

        Kept for API consistency with other tabs so ``ModernMainWindow`` can
        iterate over all tabs and call this method uniformly.

        Args:
            enabled: ``True`` if advanced mode is active.
        """
        self.advanced_mode = enabled

    def _browse_file(self):
        """Open the system file picker and load the selected file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select ISBN Input File",
            "",
            "All Files (*.*);;Excel Files (*.xlsx *.xls);;TSV Files (*.tsv);;Text Files (*.txt);;CSV Files (*.csv)"
        )

        if file_path:
            self._load_file(file_path)

    def _handle_file_drop(self, file_path):
        """Slot for ``ClickableDropZone.fileDropped`` — delegates to ``_load_file``.

        Args:
            file_path: Absolute path string emitted by the drop zone.
        """
        self._load_file(file_path)

    def _load_file(self, file_path):
        """Store the selected file path, update the UI controls, and emit ``file_selected``.

        Args:
            file_path: Absolute path string from a file-dialog or drop event.
        """
        self.input_file = Path(file_path)
        self.file_path_edit.setText(str(self.input_file))
        self._load_file_preview()
        self._update_file_info()
        self.file_selected.emit(str(self.input_file))

    def _load_file_preview(self):
        """Read up to ``PREVIEW_MAX_LINES`` lines and populate the preview text widget."""
        if not self.input_file or not self.input_file.exists():
            return

        try:
            with open(self.input_file, 'r', encoding='utf-8-sig') as f:
                lines = list(islice(f, PREVIEW_MAX_LINES))
                preview_text = ''.join(lines)
                if len(lines) == PREVIEW_MAX_LINES:
                    preview_text += "\n... (truncated)"
                self.preview_text.setPlainText(preview_text)
        except Exception as e:
            self.preview_text.setPlainText(f"Error reading file: {str(e)}")

    def _update_file_info(self):
        """Scan the input file and populate the File Information summary panel.

        For very large files (> ``LARGE_FILE_THRESHOLD_BYTES``) only the first
        ``INFO_SAMPLE_MAX_LINES`` lines are sampled and a note is appended.
        Skips blank lines, comment lines starting with ``#``, and the first
        header row if it matches a known ISBN column-header token.
        """
        if not self.input_file or not self.input_file.exists():
            return

        try:
            total_nonempty = 0
            candidate_rows = 0
            valid_rows = 0
            invalid_rows = 0
            seen: set[str] = set()
            unique_valid = 0
            file_size = self.input_file.stat().st_size
            # Sample large files to avoid blocking the UI for many seconds.
            sampled = file_size > LARGE_FILE_THRESHOLD_BYTES

            with open(self.input_file, 'r', encoding='utf-8-sig') as f:
                first_data_row_seen = False
                for i, line in enumerate(f, start=1):
                    raw_line = line.strip()
                    if not raw_line:
                        continue
                    total_nonempty += 1

                    # First column only; tabs separate additional columns.
                    raw_isbn = raw_line.split("\t")[0].strip()
                    if not raw_isbn:
                        continue

                    # Lines starting with "#" are treated as comments.
                    if raw_isbn.startswith("#"):
                        continue

                    # Skip a recognised header token on the very first data row.
                    if not first_data_row_seen and raw_isbn.lower() in {"isbn", "isbns", "isbn13", "isbn10"}:
                        first_data_row_seen = True
                        continue

                    first_data_row_seen = True
                    candidate_rows += 1

                    normalized = normalize_isbn(raw_isbn)
                    if not normalized:
                        invalid_rows += 1
                        continue

                    valid_rows += 1
                    # Track seen ISBNs to compute the unique count.
                    if normalized not in seen:
                        seen.add(normalized)
                        unique_valid += 1

                    if sampled and i >= INFO_SAMPLE_MAX_LINES:
                        break

            duplicate_valid_rows = max(0, valid_rows - unique_valid)
            sample_note = ""
            if sampled:
                sample_note = (
                    f"\nNote: Large file detected. Statistics are based on the first "
                    f"{INFO_SAMPLE_MAX_LINES:,} lines."
                )

            info_text = (
                f"File: {self.input_file.name}\n"
                f"Size: {self.input_file.stat().st_size / 1024:.2f} KB\n"
                f"Valid ISBNs (unique): {unique_valid}\n"
                f"Valid ISBN rows: {valid_rows}\n"
                f"Duplicate valid rows: {duplicate_valid_rows}\n"
                f"Invalid ISBN rows: {invalid_rows}"
                f"{sample_note}"
            )
            self.info_label.setText(info_text)
        except Exception as e:
            self.info_label.setText(f"Error reading file: {str(e)}")

    def get_input_file(self):
        """Return the absolute path of the selected input file as a string, or ``None``."""
        return str(self.input_file) if self.input_file else None

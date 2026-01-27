"""
Module: input_tab.py
Input file selection tab for ISBN list.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QGroupBox,
    QTextEdit, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from pathlib import Path


class InputTab(QWidget):
    file_selected = pyqtSignal(str)  # Emits file path when selected

    def __init__(self):
        super().__init__()
        self.input_file = None
        self.setAcceptDrops(True)  # Enable drag & drop
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()

        # Title
        title_label = QLabel("Input File Selection")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title_label)

        # Instructions
        instructions = QLabel(
            "Select a file containing ISBNs to process. The file should be:\n"
            "• Tab-separated values (TSV) format\n"
            "• First column contains ISBN numbers\n"
            "• ISBNs can be 10 or 13 digits, with or without hyphens"
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Drag & Drop Zone
        self.drop_zone = QFrame()
        self.drop_zone.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)
        self.drop_zone.setAcceptDrops(True)
        self.drop_zone.setStyleSheet("""
            QFrame {
                border: 3px dashed #0066cc;
                border-radius: 10px;
                background-color: #f0f8ff;
                min-height: 120px;
            }
            QFrame:hover {
                background-color: #e6f2ff;
                border-color: #0052a3;
            }
        """)

        drop_layout = QVBoxLayout()
        drop_icon = QLabel("📁")
        drop_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_icon.setStyleSheet("font-size: 48px; border: none;")

        drop_text = QLabel("Drag & Drop ISBN File Here\nor click Browse below")
        drop_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_text.setStyleSheet("font-size: 14px; color: #0066cc; font-weight: bold; border: none;")

        drop_hint = QLabel("Supports: .tsv, .txt, .csv files")
        drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_hint.setStyleSheet("font-size: 11px; color: #666666; border: none;")

        drop_layout.addWidget(drop_icon)
        drop_layout.addWidget(drop_text)
        drop_layout.addWidget(drop_hint)

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
        info_layout.addWidget(self.info_label)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        layout.addStretch()
        self.setLayout(layout)
        self.advanced_mode = False

    def set_advanced_mode(self, enabled):
        """Enable/disable advanced mode features."""
        self.advanced_mode = enabled
        # Input tab doesn't have many advanced features yet
        # but we keep the method for consistency

    def _browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select ISBN Input File",
            "",
            "TSV Files (*.tsv);;Text Files (*.txt);;All Files (*.*)"
        )

        if file_path:
            self.input_file = Path(file_path)
            self.file_path_edit.setText(str(self.input_file))
            self._load_file_preview()
            self._update_file_info()
            self.file_selected.emit(str(self.input_file))

    def _load_file_preview(self):
        if not self.input_file or not self.input_file.exists():
            return

        try:
            with open(self.input_file, 'r', encoding='utf-8-sig') as f:
                lines = f.readlines()[:20]  # Preview first 20 lines
                preview_text = ''.join(lines)
                if len(lines) == 20:
                    preview_text += "\n... (truncated)"
                self.preview_text.setPlainText(preview_text)
        except Exception as e:
            self.preview_text.setPlainText(f"Error reading file: {str(e)}")

    def _update_file_info(self):
        if not self.input_file or not self.input_file.exists():
            return

        try:
            with open(self.input_file, 'r', encoding='utf-8-sig') as f:
                lines = [line.strip() for line in f if line.strip()]

            # Filter out potential header
            if lines and lines[0].lower() in ['isbn', 'isbns', 'isbn13', 'isbn10']:
                lines = lines[1:]

            info_text = (
                f"File: {self.input_file.name}\n"
                f"Size: {self.input_file.stat().st_size / 1024:.2f} KB\n"
                f"Approximate ISBN count: {len(lines)}"
            )
            self.info_label.setText(info_text)
        except Exception as e:
            self.info_label.setText(f"Error reading file: {str(e)}")

    def get_input_file(self):
        """Return the selected input file path."""
        return str(self.input_file) if self.input_file else None

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter event."""
        if event.mimeData().hasUrls():
            # Check if any of the files are valid
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path.endswith(('.tsv', '.txt', '.csv')):
                    event.acceptProposedAction()
                    self.drop_zone.setStyleSheet("""
                        QFrame {
                            border: 3px dashed #00cc66;
                            border-radius: 10px;
                            background-color: #e6ffe6;
                            min-height: 120px;
                        }
                    """)
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        """Handle drag leave event."""
        self.drop_zone.setStyleSheet("""
            QFrame {
                border: 3px dashed #0066cc;
                border-radius: 10px;
                background-color: #f0f8ff;
                min-height: 120px;
            }
            QFrame:hover {
                background-color: #e6f2ff;
                border-color: #0052a3;
            }
        """)

    def dropEvent(self, event: QDropEvent):
        """Handle drop event."""
        files = [url.toLocalFile() for url in event.mimeData().urls()]

        # Filter valid files
        valid_files = [f for f in files if f.endswith(('.tsv', '.txt', '.csv'))]

        if valid_files:
            # Use the first valid file
            file_path = valid_files[0]
            self.input_file = Path(file_path)
            self.file_path_edit.setText(str(self.input_file))
            self._load_file_preview()
            self._update_file_info()
            self.file_selected.emit(str(self.input_file))

            # Animate success
            self.drop_zone.setStyleSheet("""
                QFrame {
                    border: 3px solid #00cc66;
                    border-radius: 10px;
                    background-color: #d4ffd4;
                    min-height: 120px;
                }
            """)

            # Reset after delay
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(500, lambda: self.drop_zone.setStyleSheet("""
                QFrame {
                    border: 3px dashed #0066cc;
                    border-radius: 10px;
                    background-color: #f0f8ff;
                    min-height: 120px;
                }
                QFrame:hover {
                    background-color: #e6f2ff;
                    border-color: #0052a3;
                }
            """))

            event.acceptProposedAction()
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Invalid File",
                "Please drop a valid TSV, TXT, or CSV file."
            )
            event.ignore()

        self.dragLeaveEvent(event)

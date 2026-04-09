"""Modal dialog for adding and editing Z39.50 harvest targets.

``TargetDialog`` is opened by ``TargetsTab`` in two modes:

* **Add mode** (``target=None``) — the form starts blank and the rank spin box
  defaults to the last position (``total_targets``).
* **Edit mode** (``target=<Target>``) — the form is pre-populated with the
  existing values and a "Remove" button is added to the button bar.

After ``exec()`` returns, the caller inspects two state flags:

* ``remove_requested`` — set to ``True`` if the user clicked "Remove"; the
  caller should delete the target and skip reading ``get_data()``.
* ``connection_status`` — the boolean result of the last connectivity test, or
  ``None`` if no test was performed; used to pre-populate the server-status
  cache in ``TargetsTab``.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from src.utils.targets_manager import Target
from src.z3950.session_manager import validate_connection

from .theme_manager import ThemeManager


class TargetDialog(QDialog):
    """Modal form for collecting and validating a single Z39.50 target's settings.

    The dialog performs a live connectivity probe (``validate_connection``)
    both from the "Test Connection" button and implicitly on "OK".  If the probe
    fails the user is asked whether to save the target anyway — the dialog never
    blocks a save silently.

    Attributes:
        connection_status (bool | None): Result of the last connectivity test.
            ``None`` if no test has been run.
        remove_requested (bool): Set to ``True`` when the user clicks "Remove"
            inside an edit session.  The caller must check this flag before
            reading ``get_data()``.
    """

    def __init__(self, parent=None, target: Target | None = None, total_targets: int = 1):
        """Initialise the dialog.

        Args:
            parent: Parent widget; ``None`` for a top-level dialog.
            target: Existing target to edit, or ``None`` for a new target.
            total_targets: Total number of targets (including the new one for
                           add-mode) so the rank spin box range is correct.
        """
        super().__init__(parent)
        self.setWindowTitle("Add Target" if target is None else "Edit Target")
        self.target = target
        self.total_targets = total_targets
        self.connection_status = None   # populated by test_connection / try_accept
        self.remove_requested = False   # set by _on_remove_clicked
        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self):
        """Build the form layout with fields for each editable target attribute."""
        layout = QVBoxLayout()
        form_layout = QFormLayout()

        # Pre-populate every field with the existing target's values in edit mode;
        # leave blank (or default) in add mode.
        self.name_edit = QLineEdit(self.target.name if self.target else "")
        self.host_edit = QLineEdit(self.target.host if self.target else "")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        # Z39.50 conventional port is 210; use it as the default for new targets.
        self.port_spin.setValue(self.target.port if self.target and self.target.port else 210)
        self.database_edit = QLineEdit(self.target.database if self.target else "")

        # Rank range spans the full target list so the user can pick any slot.
        # For add-mode the new slot is already included in total_targets (+1 was
        # applied by the caller), so the new target defaults to the last position.
        self.rank_spin = QSpinBox()
        self.rank_spin.setRange(1, self.total_targets)
        if self.target:
            self.rank_spin.setValue(self.target.rank if self.target.rank else 1)
        else:
            # Default new targets to the last rank position.
            self.rank_spin.setValue(self.total_targets)

        form_layout.addRow("Target Name:", self.name_edit)
        form_layout.addRow("Host Address:", self.host_edit)
        form_layout.addRow("Port:", self.port_spin)
        form_layout.addRow("Database Name:", self.database_edit)
        form_layout.addRow("Rank:", self.rank_spin)

        layout.addLayout(form_layout)

        self.btn_test = QPushButton("Test Connection")
        self.btn_test.clicked.connect(self.test_connection)
        layout.addWidget(self.btn_test)

        bottom_layout = QHBoxLayout()
        # "Remove" button is only shown in edit mode; objectName triggers the
        # DangerButton (red) rule in the dialog's inline stylesheet.
        if self.target is not None:
            self.btn_remove_dlg = QPushButton("Remove")
            self.btn_remove_dlg.setObjectName("DangerButton")
            self.btn_remove_dlg.clicked.connect(self._on_remove_clicked)
            bottom_layout.addWidget(self.btn_remove_dlg)

        bottom_layout.addStretch()

        # Standard Ok/Cancel pair — Ok is wired to try_accept (validates before
        # accepting) rather than self.accept to allow the connectivity check.
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.try_accept)
        buttons.rejected.connect(self.reject)
        bottom_layout.addWidget(buttons)

        layout.addLayout(bottom_layout)
        self.setLayout(layout)

    def test_connection(self):
        """Manually test the current host/port values and report the result."""
        host = self.host_edit.text().strip()
        port = self.port_spin.value()
        database = self.database_edit.text().strip()

        if not host:
            QMessageBox.warning(self, "Input Error", "Please enter a host to test.")
            return

        self.setCursor(Qt.CursorShape.WaitCursor)
        success = validate_connection(host, port)
        self.unsetCursor()

        self.connection_status = success
        address = f"{host}:{port}/{database}" if database else f"{host}:{port}"

        if success:
            QMessageBox.information(self, "Success", f"Successfully connected to {address}")
            return

        QMessageBox.critical(
            self,
            "Connection Failed",
            f"Could not connect to {address}.\nPlease check the details and try again.",
        )

    def try_accept(self):
        """Validate the form and allow the user to save even if the host is offline."""
        host = self.host_edit.text().strip()
        port = self.port_spin.value()
        database = self.database_edit.text().strip()

        if not self.name_edit.text().strip() or not host:
            QMessageBox.warning(self, "Validation Error", "Name and Host are required.")
            return

        self.setCursor(Qt.CursorShape.WaitCursor)
        success = validate_connection(host, port)
        self.unsetCursor()

        self.connection_status = success
        address = f"{host}:{port}/{database}" if database else f"{host}:{port}"

        if success:
            self.accept()
            return

        reply = QMessageBox.question(
            self,
            "Connection Failed",
            f"Could not connect to {address}.\n\nDo you want to save this target anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.accept()

    def get_data(self):
        """Return the entered target settings in a form the tab can persist.

        Returns:
            A dict with keys ``name``, ``host``, ``port``, ``database``,
            ``rank``.  All string values are stripped of leading/trailing
            whitespace.
        """
        return {
            "name": self.name_edit.text().strip(),
            "host": self.host_edit.text().strip(),
            "port": self.port_spin.value(),
            "database": self.database_edit.text().strip(),
            "rank": self.rank_spin.value(),
        }

    def get_connection_status(self):
        """Return the latest connection test result."""
        return self.connection_status

    def _on_remove_clicked(self):
        """Flag that remove was requested and close the dialog."""
        self.remove_requested = True
        self.reject()

    def _apply_styles(self):
        """Apply lightweight theme-aware inline stylesheet to dialog controls.

        The dialog is not connected to the global QApplication stylesheet so it
        carries its own self-contained rules.  SVG icon ``url()`` references use
        a relative path in the template string that is rewritten to an absolute
        POSIX path at runtime so the QSS engine can resolve them on all
        platforms.
        """
        mode = ThemeManager().get_theme()
        # Build an absolute POSIX path to the icons directory; QSS url() requires
        # forward slashes on all platforms.
        icons_dir = (Path(__file__).parent / "icons").as_posix()
        if mode == "dark":
            # Dark branch — Catppuccin Mocha palette colours.
            # Structure of this QSS block:
            #   QDialog          — deep background (#1e1e2e) and text (#cdd6f4)
            #   QLabel           — same text colour + bold weight for form labels
            #   QLineEdit/Spin   — slightly lighter surface (#313244) with border
            #   QSpinBox arrows  — custom plus/minus SVG icons (path resolved below)
            #   QPushButton      — generic neutral button + #DangerButton red variant
            self.setStyleSheet(
                """
                QDialog {
                    background-color: #1e1e2e;
                    color: #cdd6f4;
                }
                QLabel {
                    color: #cdd6f4;
                    font-weight: bold;
                }
                QLineEdit, QSpinBox {
                    background-color: #313244;
                    border: 1px solid #45475a;
                    border-radius: 4px;
                    padding: 6px;
                    color: #ffffff;
                }
                QSpinBox::up-button, QSpinBox::down-button {
                    width: 20px;
                    background-color: #313244;
                    border: none;
                    border-left: 1px solid #45475a;
                }
                QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                    background-color: #45475a;
                }
                QSpinBox::up-arrow {
                    width: 12px;
                    height: 12px;
                    image: url(src/gui/icons/plus.svg);
                    border: none;
                }
                QSpinBox::down-arrow {
                    width: 12px;
                    height: 12px;
                    image: url(src/gui/icons/minus.svg);
                    border: none;
                }
                QLineEdit:focus, QSpinBox:focus {
                    border: 1px solid #89b4fa;
                }
                QPushButton {
                    background-color: #313244;
                    color: white;
                    border: 1px solid #45475a;
                    padding: 6px 12px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #45475a;
                }
                QPushButton#DangerButton {
                    background-color: #ed8796;
                    color: #1e1e2e;
                    border: 1px solid #d97082;
                }
                QPushButton#DangerButton:hover {
                    background-color: #d97082;
                }
            # Replace the relative icon path prefix with the resolved absolute
            # path so QSS can find the SVG files regardless of the cwd.
            """.replace("url(src/gui/icons/", f"url({icons_dir}/")
            )
            return

        # Light branch — Tailwind Slate palette colours.
        # Structure mirrors the dark branch above with lighter surface values.
        self.setStyleSheet(
            """
            QDialog {
                background-color: #ffffff;
                color: #0f172a;
            }
            QLabel {
                color: #0f172a;
                font-weight: bold;
            }
            QLineEdit, QSpinBox {
                background-color: #f3f4f6;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 6px;
                color: #0f172a;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 20px;
                background-color: #f3f4f6;
                border: none;
                border-left: 1px solid #cbd5e1;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background-color: #e2e8f0;
            }
            QSpinBox::up-arrow {
                width: 12px;
                height: 12px;
                image: url(src/gui/icons/plus.svg);
                border: none;
            }
            QSpinBox::down-arrow {
                width: 12px;
                height: 12px;
                image: url(src/gui/icons/minus.svg);
                border: none;
            }
            QLineEdit:focus, QSpinBox:focus {
                border: 1px solid #3b82f6;
            }
            QPushButton {
                background-color: #f1f5f9;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
            }
            QPushButton#DangerButton {
                background-color: #dc2626;
                color: #ffffff;
                border: 1px solid #b91c1c;
            }
            QPushButton#DangerButton:hover {
                background-color: #b91c1c;
            }
        # Same path substitution as the dark branch above.
        """.replace("url(src/gui/icons/", f"url({icons_dir}/")
        )

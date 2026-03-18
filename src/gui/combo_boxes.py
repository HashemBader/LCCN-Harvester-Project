"""
Shared combo box helpers for the PyQt6 GUI.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QListView


class ConsistentComboBox(QComboBox):
    """A combo box with predictable popup styling and safer wheel behavior."""

    def __init__(
        self,
        parent=None,
        *,
        popup_object_name: str | None = None,
        max_visible_items: int | None = None,
    ):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

        popup_view = QListView(self)
        popup_view.setUniformItemSizes(True)
        if popup_object_name:
            popup_view.setObjectName(popup_object_name)
        self.setView(popup_view)

        if max_visible_items is not None:
            try:
                self.setMaxVisibleItems(max(1, int(max_visible_items)))
            except Exception:
                self.setMaxVisibleItems(10)

    def wheelEvent(self, event):
        """Ignore wheel changes unless the combo box already has focus."""
        if self.hasFocus():
            super().wheelEvent(event)
            return
        event.ignore()


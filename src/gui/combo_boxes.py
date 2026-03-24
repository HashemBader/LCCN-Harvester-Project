"""
Shared combo box helpers for the PyQt6 GUI.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QListView, QFrame


class ConsistentComboBox(QComboBox):
    """A combo box with predictable popup styling and safer wheel behavior."""

    DEFAULT_POPUP_OBJECT_NAME = "ComboPopup"

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
        popup_view.setFrameShape(QFrame.Shape.NoFrame)
        popup_view.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        popup_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        popup_view.setObjectName(popup_object_name or self.DEFAULT_POPUP_OBJECT_NAME)
        self.setView(popup_view)

        if max_visible_items is not None:
            try:
                self.setMaxVisibleItems(max(1, int(max_visible_items)))
            except Exception:
                self.setMaxVisibleItems(10)

    def showPopup(self):
        """Normalize popup sizing so combo menus render consistently on every platform."""
        popup_view = self.view()
        if popup_view is not None:
            try:
                content_width = popup_view.sizeHintForColumn(0)
            except Exception:
                content_width = -1

            scrollbar_width = 0
            try:
                scrollbar_width = popup_view.verticalScrollBar().sizeHint().width()
            except Exception:
                scrollbar_width = 0

            frame_width = 0
            try:
                frame_width = popup_view.frameWidth() * 2
            except Exception:
                frame_width = 0

            desired_width = max(self.width(), content_width + scrollbar_width + frame_width + 28)
            popup_view.setMinimumWidth(desired_width)

        super().showPopup()

    def wheelEvent(self, event):
        """Ignore wheel changes unless the combo box already has focus."""
        if self.hasFocus():
            super().wheelEvent(event)
            return
        event.ignore()

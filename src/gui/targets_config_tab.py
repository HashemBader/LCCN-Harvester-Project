"""Combined Configure page — profile settings (top) + target list (bottom).

``TargetsConfigTab`` composes ``ConfigTab`` and ``TargetsTab`` inside a vertical
``QSplitter`` so the user can resize the two panes.  It acts as a thin facade:
signals from the inner tabs are re-emitted on this widget so that
``ModernMainWindow`` only needs to connect to one object.

The splitter is initialised with a 150/650 ratio so the compact settings row
receives just enough height while the target table gets most of the space.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSplitter
from PyQt6.QtCore import Qt, pyqtSignal
from .targets_tab import TargetsTab
from .config_tab import ConfigTab


class TargetsConfigTab(QWidget):
    """Facade widget that combines ``ConfigTab`` (settings) and ``TargetsTab`` (targets).

    Signals are forwarded from the inner tabs so external code only needs to
    connect to this single widget.

    Signals:
        targets_changed(list): Re-emitted from ``TargetsTab.targets_changed``.
        profile_selected(str): Re-emitted from ``TargetsTab.profile_selected``.
        config_changed(dict): Re-emitted from ``ConfigTab.config_changed``.
        profile_changed(str): Re-emitted from ``ConfigTab.profile_changed``.
    """

    targets_changed = pyqtSignal(list)
    profile_selected = pyqtSignal(str)
    config_changed = pyqtSignal(dict)
    profile_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._setup_ui()
        self._connect_internal_signals()

    def _setup_ui(self):
        """Build the vertical splitter with ConfigTab on top and TargetsTab on the bottom."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        # Prevent either pane from being fully collapsed by dragging the handle.
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(6)
        self.config_tab = ConfigTab()
        self.targets_tab = TargetsTab()
        self.splitter.addWidget(self.config_tab)
        self.splitter.addWidget(self.targets_tab)
        # Give the compact settings row a fixed ~150 px and let the table take the rest.
        self.splitter.setSizes([150, 650])
        self.splitter.setStretchFactor(0, 0)  # ConfigTab: fixed height
        self.splitter.setStretchFactor(1, 1)  # TargetsTab: grows with the window
        layout.addWidget(self.splitter)

    def _connect_internal_signals(self):
        """Forward inner-tab signals to this widget's own signals and install the mutation guard."""
        self.targets_tab.targets_changed.connect(self.targets_changed)
        self.targets_tab.profile_selected.connect(self.profile_selected)
        self.config_tab.config_changed.connect(self.config_changed)
        self.config_tab.profile_changed.connect(self.profile_changed)
        # The mutation guard prompts for unsaved changes before allowing target edits.
        self.targets_tab.before_mutation = self._resolve_before_target_change

    # ------------------------------------------------------------------
    # Delegation helpers — thin pass-through to the inner tabs
    # ------------------------------------------------------------------

    def get_config(self):
        """Return the current profile configuration dict from ConfigTab."""
        return self.config_tab.get_config()

    def get_targets(self):
        """Return the current targets list from TargetsTab."""
        return self.targets_tab.get_targets()

    def refresh_targets_preview(self, targets=None):
        """Refresh the targets preview area inside ConfigTab."""
        self.config_tab.refresh_targets_preview(targets)

    def load_profile_targets(self, profile_name):
        """Reload the target list for the given profile in TargetsTab."""
        self.targets_tab.load_profile_targets(profile_name)

    def select_profile(self, name):
        """Select the named profile in the ConfigTab profile combo."""
        return self.config_tab.select_profile(name)

    def list_profile_names(self):
        """Return all available profile names from ConfigTab."""
        return self.config_tab.list_profile_names()

    def set_profile_options(self, profiles, current):
        """Forward profile list updates to TargetsTab."""
        self.targets_tab.set_profile_options(profiles, current)

    def set_advanced_mode(self, enabled):
        """Forward advanced-mode toggle to TargetsTab."""
        self.targets_tab.set_advanced_mode(enabled)

    def refresh_targets(self):
        """Reload and redraw the targets table in TargetsTab."""
        self.targets_tab.refresh_targets()

    def resolve_unsaved_changes(self, action_label: str = "continue") -> bool:
        """Ask the user to save or discard unsaved profile settings before proceeding.

        Args:
            action_label: Verb shown in the prompt (e.g. ``"continue"``).

        Returns:
            ``True`` if the caller may proceed, ``False`` if the user cancelled.
        """
        return self.config_tab.resolve_unsaved_changes(action_label)

    def _resolve_before_target_change(self, action_label: str = "change targets") -> bool:
        """Mutation guard installed on ``TargetsTab.before_mutation``.

        Ensures the user resolves unsaved profile settings before structural target
        changes (add/remove/reorder) are committed.
        """
        return self.config_tab.resolve_unsaved_changes(action_label)

    def create_new_profile(self):
        """Delegate the new-profile creation flow to ``ConfigTab``."""
        self.config_tab.create_new_profile()

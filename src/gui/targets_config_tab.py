from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSplitter
from PyQt6.QtCore import Qt, pyqtSignal
from .targets_tab_v2 import TargetsTabV2
from .config_tab_v2 import ConfigTabV2


class TargetsConfigTab(QWidget):
    targets_changed = pyqtSignal(list)
    profile_selected = pyqtSignal(str)
    config_changed = pyqtSignal(dict)
    profile_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._setup_ui()
        self._connect_internal_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(6)
        self.config_tab = ConfigTabV2()
        self.targets_tab = TargetsTabV2()
        self.splitter.addWidget(self.config_tab)
        self.splitter.addWidget(self.targets_tab)
        self.splitter.setSizes([260, 540])
        layout.addWidget(self.splitter)

    def _connect_internal_signals(self):
        self.targets_tab.targets_changed.connect(self.targets_changed)
        self.targets_tab.profile_selected.connect(self.profile_selected)
        self.config_tab.config_changed.connect(self.config_changed)
        self.config_tab.profile_changed.connect(self.profile_changed)

    def get_config(self):
        return self.config_tab.get_config()

    def get_targets(self):
        return self.targets_tab.get_targets()

    def refresh_targets_preview(self, targets=None):
        self.config_tab.refresh_targets_preview(targets)

    def load_profile_targets(self, profile_name):
        self.targets_tab.load_profile_targets(profile_name)

    def select_profile(self, name):
        return self.config_tab.select_profile(name)

    def list_profile_names(self):
        return self.config_tab.list_profile_names()

    def set_profile_options(self, profiles, current):
        self.targets_tab.set_profile_options(profiles, current)

    def set_advanced_mode(self, enabled):
        self.targets_tab.set_advanced_mode(enabled)

    def refresh_targets(self):
        self.targets_tab.refresh_targets()

    def create_new_profile(self):
        self.config_tab.create_new_profile()

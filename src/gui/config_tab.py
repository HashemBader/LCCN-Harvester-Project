"""Configuration page — profile management and harvest settings.

This module contains two widgets:

``CreateProfileDialog``
    A modal dialog that collects a new profile name, an optional source profile
    to copy settings from, and starting values for retry interval and call-number
    mode.  Accepted via ``QDialogButtonBox`` with custom validation.  Signals on
    the spin/combo are blocked during source-profile population to avoid spurious
    dirty-change events.

``ConfigTab``
    The settings pane that sits in the upper half of ``TargetsConfigTab``'s
    vertical splitter.  It lets the user switch between saved profiles, edit
    the retry interval and call-number mode for the active profile, and
    create/delete profiles.  All changes are dirty-tracked (``has_unsaved_changes``)
    so the user is prompted before navigating away from unsaved work.

    The ``stop_rule_combo`` is intentionally hidden on this page; it is kept as a
    round-trip storage vehicle so ``get_config`` / ``_save_current_profile`` can
    persist the stop-rule value that is edited in ``HarvestTab``'s own UI.

Signals emitted:
    ``config_changed(dict)`` — whenever a setting is modified but not yet saved.
    ``profile_changed(str)`` — when the active profile is switched or a new one
        is created/deleted.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QComboBox,
    QSpinBox, QMessageBox, QDialog, QDialogButtonBox, QLineEdit,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
import shutil

from src.config.profile_manager import ProfileManager
from .combo_boxes import ConsistentComboBox
from .icons import get_pixmap, SVG_SETTINGS, SVG_HARVEST
from .styles import CATPPUCCIN_THEME


class CreateProfileDialog(QDialog):
    """Modal dialog for creating a new harvest profile.

    Lets the user choose a name, select a source profile to copy settings from,
    and optionally override the retry interval and call-number mode before
    clicking "Create Profile".

    Key widgets:
        source_combo: Profile to copy settings and targets from.
        name_edit: Text field for the new profile name.
        retry_spin: QSpinBox pre-filled with the source profile's retry interval.
        mode_combo: Call-number mode combo pre-filled from the source profile.
    """

    def __init__(self, profile_manager: ProfileManager, parent=None, initial_source="Default Settings"):
        """
        Args:
            profile_manager: Application-wide ``ProfileManager`` instance used to
                enumerate existing profiles and load their settings.
            parent: Optional parent widget.
            initial_source: Profile name to pre-select in the source combo (defaults
                to ``"Default Settings"``).
        """
        super().__init__(parent)
        self.profile_manager = profile_manager
        self.setWindowTitle("Create Profile")
        self.setModal(True)
        self.setMinimumWidth(480)
        self._selected_source = initial_source or "Default Settings"
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QLabel("Create New Profile")
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; ")
        layout.addWidget(title)

        subtitle = QLabel("Choose a profile name and starting settings.")
        subtitle.setStyleSheet(f" font-size: 12px;")
        layout.addWidget(subtitle)

        source_label = QLabel("Copy Settings And Targets From")
        source_label.setStyleSheet(f"font-weight: 600; ")
        layout.addWidget(source_label)

        self.source_combo = ConsistentComboBox()
        self.source_combo.addItems(self.profile_manager.list_profiles())
        source_index = self.source_combo.findText(self._selected_source)
        self.source_combo.setCurrentIndex(source_index if source_index >= 0 else 0)
        self.source_combo.currentTextChanged.connect(self._on_source_changed)
        layout.addWidget(self.source_combo)

        name_label = QLabel("Profile Name")
        name_label.setStyleSheet(f"font-weight: 600; ")
        layout.addWidget(name_label)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g., Quick Harvest / Medical / Batch Retry")
        self.name_edit.setClearButtonEnabled(True)
        layout.addWidget(self.name_edit)

        settings_frame = QFrame()
        settings_frame.setProperty("class", "Card")
        settings_layout = QVBoxLayout(settings_frame)
        settings_layout.setContentsMargins(14, 14, 14, 14)
        settings_layout.setSpacing(12)

        settings_title = QLabel("Starting Settings")
        settings_title.setStyleSheet(f"font-weight: 700; ")
        settings_layout.addWidget(settings_title)

        retry_row = QHBoxLayout()
        retry_label = QLabel("Retry Interval")
        retry_label.setStyleSheet("")
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 365)
        self.retry_spin.setSuffix(" days")
        self.retry_spin.setFixedWidth(120)
        retry_row.addWidget(retry_label)
        retry_row.addStretch()
        retry_row.addWidget(self.retry_spin)
        settings_layout.addLayout(retry_row)

        mode_row = QHBoxLayout()
        mode_label = QLabel("Call Number Selection")
        mode_label.setStyleSheet("")
        self.mode_combo = ConsistentComboBox()
        self.mode_combo.setFixedWidth(180)
        self.mode_combo.addItem("LCCN only", "lccn")
        self.mode_combo.addItem("NLMCN only", "nlmcn")
        self.mode_combo.addItem("Both", "both")
        mode_row.addWidget(mode_label)
        mode_row.addStretch()
        mode_row.addWidget(self.mode_combo)
        settings_layout.addLayout(mode_row)


        layout.addWidget(settings_frame)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Create Profile")
        ok_btn.setProperty("class", "PrimaryButton")
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_btn.setProperty("class", "SecondaryButton")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Inherit app theme — no hardcoded colours
        self._on_source_changed(self.source_combo.currentText())

    def _validate_and_accept(self):
        """Validate that a non-empty profile name was entered before accepting the dialog."""
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Missing Name", "Please enter a profile name.")
            self.name_edit.setFocus()
            return
        self.accept()

    def _load_source_settings(self, source_name: str) -> dict:
        """Load the settings dict for *source_name* from the profile manager.

        Returns an empty dict if the profile does not exist or has no settings key.
        """
        profile = self.profile_manager.load_profile(source_name)
        settings = profile.get("settings", {}) if isinstance(profile, dict) else {}
        if not isinstance(settings, dict):
            settings = {}
        return settings

    def _on_source_changed(self, source_name: str):
        """Populate the starting-settings controls from the newly selected source profile.

        Signals on the spin/combo are blocked during population to avoid triggering
        unsaved-changes logic in the parent dialog.  ``findData`` is used to match the
        combo by the internal data value (e.g. ``"lccn"``) rather than the display text.
        """
        self._selected_source = source_name or "Default Settings"
        settings = self._load_source_settings(self._selected_source)
        # Block signals to prevent spurious change notifications while pre-filling.
        self.retry_spin.blockSignals(True)
        self.mode_combo.blockSignals(True)
        self.retry_spin.setValue(int(settings.get("retry_days", 7)))
        mode = settings.get("call_number_mode", "lccn")
        # findData looks up by the item's UserRole data (the mode string), not the label.
        idx = self.mode_combo.findData(mode)
        self.mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.retry_spin.blockSignals(False)
        self.mode_combo.blockSignals(False)

    def profile_name(self) -> str:
        """Return the stripped profile name entered by the user."""
        return self.name_edit.text().strip()

    def source_profile_name(self) -> str:
        """Return the name of the profile whose settings will be copied."""
        return self._selected_source or "Default Settings"

    def profile_settings(self) -> dict:
        """Return the settings dict to use when creating the new profile.

        Validates the ``call_number_mode`` value against the allowed set; defaults
        to ``"lccn"`` if the combo returns an unexpected value.

        Returns:
            Dict with keys ``retry_days``, ``call_number_mode``, ``collect_lccn``,
            ``collect_nlmcn``, ``stop_rule``, ``output_tsv``, and
            ``output_invalid_isbn_file``.
        """
        mode = self.mode_combo.currentData()
        mode = mode if mode in {"lccn", "nlmcn", "both"} else "lccn"
        return {
            "retry_days": self.retry_spin.value(),
            "call_number_mode": mode,
            "collect_lccn": mode in {"lccn", "both"},
            "collect_nlmcn": mode in {"nlmcn", "both"},
            "stop_rule": "stop_either",
            "output_tsv": True,
            "output_invalid_isbn_file": True,
        }


class ConfigTab(QWidget):
    """Profile-settings pane displayed in the upper half of the Configure page splitter.

    Contains a profile selector combo with New/Save/Delete buttons, and a compact
    harvest-settings row (retry interval, call-number mode).

    Key instance variables:
        profile_manager (ProfileManager): Shared profile storage/retrieval helper.
        current_profile_name (str): Name of the currently loaded profile.
        has_unsaved_changes (bool): ``True`` when a control has been edited since the
            last save or load; drives the "Save Changes" button's enabled state.

    Key widgets built by ``_setup_ui``:
        profile_combo: Active-profile selector.
        btn_new / btn_save / btn_delete: Profile management buttons.
        spin_retry: Retry-interval spin box (0–365 days).
        call_number_combo: Call-number mode selector (LCCN/NLMCN/Both).
        stop_rule_combo: Hidden combo that round-trips the stop-rule setting; the
            visible control lives in ``HarvestTab``.

    Signals:
        config_changed(dict): Emitted whenever a setting control is modified.
        profile_changed(str): Emitted when the active profile is switched, created,
            or deleted.
    """

    # Emitted with the current get_config() dict whenever a control value changes.
    config_changed = pyqtSignal(dict)
    # Emitted with the new profile name when the active profile changes.
    profile_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.profile_manager = ProfileManager()
        self.current_profile_name = self.profile_manager.get_active_profile()
        self.has_unsaved_changes = False  # True whenever a control is edited but not yet saved.
        self._setup_ui()
        # Populate controls with the persisted settings for the active profile.
        self._load_profile(self.current_profile_name)
        self.refresh_targets_preview()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(12, 6, 12, 6)

        # =========================================================================
        # Profile Section (Card)
        # =========================================================================
        profile_frame = QFrame()
        profile_frame.setProperty("class", "Card")
        profile_vlayout = QVBoxLayout(profile_frame)
        profile_vlayout.setSpacing(4)
        profile_vlayout.setContentsMargins(12, 6, 12, 6)

        # Row 1: Icon + Title + Profile combo + Action buttons
        profile_row = QHBoxLayout()
        profile_row.setSpacing(8)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap(SVG_SETTINGS, CATPPUCCIN_THEME['primary']))
        profile_row.addWidget(icon_lbl)

        profile_title = QLabel("Profile Settings")
        profile_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        profile_row.addWidget(profile_title)

        self.profile_combo = ConsistentComboBox()
        self.profile_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.profile_combo.setAccessibleName("Active profile selector")
        self.profile_combo.setAccessibleDescription("Choose which saved profile is active.")
        self._refresh_profile_list()
        self.profile_combo.currentTextChanged.connect(self._on_profile_selected)
        profile_row.addWidget(self.profile_combo, 1)

        self.btn_new = QPushButton("&New Profile")
        self.btn_new.setProperty("class", "SecondaryButton")
        self.btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new.setAccessibleName("Create profile")
        self.btn_new.setToolTip("Create a new profile from current settings")
        self.btn_new.clicked.connect(self._create_new_profile)

        self.btn_save = QPushButton("&Save Changes")
        self.btn_save.setProperty("class", "PrimaryButton")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setEnabled(False)
        self.btn_save.setAccessibleName("Save profile changes")
        self.btn_save.setToolTip("Save current settings to the selected profile")
        self.btn_save.clicked.connect(self._save_current_profile)

        self.btn_delete = QPushButton("&Delete")
        self.btn_delete.setProperty("class", "DangerButton")
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setAccessibleName("Delete profile")
        self.btn_delete.setToolTip("Delete the selected profile")
        self.btn_delete.clicked.connect(self._delete_current_profile)

        profile_row.addWidget(self.btn_new)
        profile_row.addWidget(self.btn_save)
        profile_row.addWidget(self.btn_delete)

        profile_vlayout.addLayout(profile_row)

        layout.addWidget(profile_frame)

        # =========================================================================
        # Harvest Settings (Card)
        # =========================================================================
        settings_frame = QFrame()
        settings_frame.setProperty("class", "Card")
        settings_row = QHBoxLayout(settings_frame)
        settings_row.setSpacing(12)
        settings_row.setContentsMargins(12, 6, 12, 6)

        harvest_icon_lbl = QLabel()
        harvest_icon_lbl.setPixmap(get_pixmap(SVG_HARVEST, CATPPUCCIN_THEME['primary']))
        settings_row.addWidget(harvest_icon_lbl)

        harvest_title = QLabel("Harvest Settings")
        harvest_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        settings_row.addWidget(harvest_title)
        settings_row.addSpacing(8)

        retry_lbl = QLabel("&Retry Interval")

        self.spin_retry = QSpinBox()
        self.spin_retry.setRange(0, 365)
        self.spin_retry.setValue(7)
        self.spin_retry.setSuffix(" days")
        self.spin_retry.setMinimumWidth(80)
        self.spin_retry.setAccessibleName("Retry interval")
        self.spin_retry.setToolTip("Days to wait before retrying recently failed ISBNs")
        # Wire value-changed signals so any edit marks the profile dirty.
        self.spin_retry.valueChanged.connect(self._on_setting_changed)
        retry_lbl.setBuddy(self.spin_retry)

        settings_row.addWidget(retry_lbl)
        settings_row.addWidget(self.spin_retry)
        settings_row.addSpacing(12)

        mode_lbl = QLabel("Call Number &Selection")

        self.call_number_combo = ConsistentComboBox()
        self.call_number_combo.setMinimumWidth(130)
        self.call_number_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.call_number_combo.setAccessibleName("Call number selection")
        self.call_number_combo.setAccessibleDescription("Choose whether to collect LCCN only, NLMCN only, or both.")
        self.call_number_combo.setToolTip("Select which call-number type is accepted during harvest")
        self.call_number_combo.addItem("LCCN only", "lccn")
        self.call_number_combo.addItem("NLMCN only", "nlmcn")
        self.call_number_combo.addItem("Both", "both")
        self.call_number_combo.currentTextChanged.connect(self._on_setting_changed)  # marks profile dirty
        mode_lbl.setBuddy(self.call_number_combo)

        settings_row.addWidget(mode_lbl)
        settings_row.addWidget(self.call_number_combo)
        settings_row.addStretch()

        # The stop-rule combo is managed in the Harvest tab's UI, not here.
        # It is kept as a hidden control so _load_profile / get_config can
        # read and write the persisted stop_rule value without touching the harvest tab.
        self.stop_rule_combo = ConsistentComboBox()
        self.stop_rule_combo.addItem("Stop if either found", "stop_either")
        self.stop_rule_combo.addItem("Stop if LCCN found", "stop_lccn")
        self.stop_rule_combo.addItem("Stop if NLMCN found", "stop_nlmcn")
        self.stop_rule_combo.addItem("Continue until both found", "continue_both")
        self.stop_rule_combo.hide()  # Not shown on this page; value is round-tripped via get_config.

        layout.addWidget(settings_frame)

    def _toggle_stop_rule_visibility(self):
        """No-op stub; stop-rule visibility is managed by ``HarvestTab`` in the current UI."""
        return None

    def refresh_targets_preview(self, targets=None):
        """No-op stub; targets are displayed live in ``TargetsTab``, not here."""
        return None

    def _create_divider(self):
        """Return a horizontal sunken QFrame to use as a visual section divider."""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet(f"background- max-height: 1px;")
        return line

    def _comparable_settings(self, settings):
        """Return a canonical subset of *settings* used for duplicate-content comparisons.

        Normalises the mode field via ``_mode_from_settings`` so legacy
        ``collect_lccn``/``collect_nlmcn`` booleans are treated equivalently to the
        modern ``call_number_mode`` string.

        Args:
            settings: Raw settings dict (may be legacy flat dict or modern nested dict).

        Returns:
            Dict with the four fields that determine whether two profiles are "the same".
        """
        if not isinstance(settings, dict):
            return {}
        mode = self._mode_from_settings(settings)
        return {
            "retry_days": int(settings.get("retry_days", 7)),
            "call_number_mode": mode,
            "collect_lccn": mode in {"lccn", "both"},
            "collect_nlmcn": mode in {"nlmcn", "both"},
        }

    def _find_profile_with_same_settings(self, candidate_settings, exclude_name: str = ""):
        """Return the first profile name whose comparable settings match *candidate_settings*.

        Args:
            candidate_settings: Settings dict to compare against.
            exclude_name: Profile name to skip (typically the one being saved, to
                avoid a false "duplicate" match with itself).

        Returns:
            Matching profile name string, or ``None`` if no duplicate is found.
        """
        normalized_candidate = self._comparable_settings(candidate_settings)
        for profile_name in self.profile_manager.list_profiles():
            if profile_name == exclude_name:
                continue
            profile = self.profile_manager.load_profile(profile_name)
            existing_settings = self._extract_profile_settings(profile)
            if self._comparable_settings(existing_settings) == normalized_candidate:
                return profile_name
        return None

    # =========================================================================
    # Logic Methods (Adapted from original ConfigTab)
    # =========================================================================
    def _extract_profile_settings(self, profile_data):
        """Normalize profile payloads from ProfileManager to a flat settings dict.

        ProfileManager returns a nested ``{"settings": {...}}`` dict.  Legacy
        profiles may have been saved as a flat dict without the ``"settings"`` key;
        this method handles both shapes.

        Args:
            profile_data: Raw payload returned by ``ProfileManager.load_profile``.

        Returns:
            Flat settings dict, or an empty dict if ``profile_data`` is not a dict.
        """
        if not isinstance(profile_data, dict):
            return {}
        settings = profile_data.get("settings")
        if isinstance(settings, dict):
            return settings
        # Backward compatibility: legacy profiles stored settings at the top level.
        return profile_data

    def _refresh_profile_list(self):
        """Repopulate the profile combo box from the profile manager without emitting signals.

        Signals are blocked so ``_on_profile_selected`` is not triggered during the
        repopulation, which would cause a recursive unsaved-changes check.
        """
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        profiles = self.profile_manager.list_profiles()
        self.profile_combo.addItems(profiles)

        # Re-select the currently active profile after repopulating.
        current = self.profile_manager.get_active_profile()
        idx = self.profile_combo.findText(current)
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)

        self.profile_combo.blockSignals(False)

    def _load_profile(self, profile_name):
        """Load *profile_name* from disk and populate all settings controls.

        Signals are blocked while the controls are populated to prevent
        ``_on_setting_changed`` from marking the profile as having unsaved changes
        immediately after loading.  On completion, emits ``profile_changed`` and
        ``config_changed`` to notify sibling tabs.

        Args:
            profile_name: Name of the profile to load (must exist in the manager).
        """
        self.current_profile_name = profile_name
        profile = self.profile_manager.load_profile(profile_name)
        config = self._extract_profile_settings(profile)

        # Block signals while populating to avoid spurious has_unsaved_changes flags.
        self.spin_retry.blockSignals(True)
        self.call_number_combo.blockSignals(True)
        
        self.spin_retry.setValue(config.get("retry_days", 7))
        mode = self._mode_from_settings(config)
        idx = self.call_number_combo.findData(mode)
        self.call_number_combo.setCurrentIndex(idx if idx >= 0 else 0)

        stop_rule = config.get("stop_rule", "stop_either")
        idx_stop = self.stop_rule_combo.findData(stop_rule)
        self.stop_rule_combo.setCurrentIndex(idx_stop if idx_stop >= 0 else 0)
        
        self.spin_retry.blockSignals(False)
        self.call_number_combo.blockSignals(False)
        
        self.has_unsaved_changes = False
        self.btn_save.setEnabled(False)
        self.profile_changed.emit(profile_name)
        self.config_changed.emit(self.get_config())

    def has_pending_changes(self) -> bool:
        """Return ``True`` if any setting has been edited but not yet saved."""
        return bool(self.has_unsaved_changes)

    def resolve_unsaved_changes(self, action_label: str = "continue") -> bool:
        """Prompt the user to save or discard pending changes before a destructive action.

        If there are no pending changes the method returns ``True`` immediately.
        For the read-only "Default Settings" profile the only option is to discard.

        Args:
            action_label: Human-readable continuation verb shown in the dialog
                (e.g. ``"switch profiles"``, ``"create a new profile"``).

        Returns:
            ``True`` if it is safe to proceed (saved or discarded), ``False`` if
            the user needs to stay on the current profile (currently never returned,
            but kept for forward compatibility).
        """
        if not self.has_unsaved_changes:
            return True

        if self.current_profile_name == "Default Settings":
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("Unsaved Changes")
            msg.setText(
                "You have unsaved changes in Default Settings.\n\n"
                "Default Settings cannot be modified, so these changes must be discarded before you "
                f"{action_label}."
            )
            discard_btn = msg.addButton("Discard Changes", QMessageBox.ButtonRole.DestructiveRole)
            discard_btn.setProperty("class", "DangerButton")
            msg.setDefaultButton(discard_btn)
            msg.exec()
            self._load_profile(self.current_profile_name)
            return True

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Unsaved Changes")
        msg.setText(
            f"You have unsaved changes in '{self.current_profile_name}'.\n\n"
            f"Do you want to save or discard them before you {action_label}?"
        )
        save_btn = msg.addButton("Save Changes", QMessageBox.ButtonRole.AcceptRole)
        discard_btn = msg.addButton("Discard Changes", QMessageBox.ButtonRole.DestructiveRole)
        save_btn.setProperty("class", "PrimaryButton")
        discard_btn.setProperty("class", "DangerButton")
        msg.setDefaultButton(save_btn)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked is save_btn:
            return self._save_current_profile(show_confirmation=False)
        self._load_profile(self.current_profile_name)
        return True

    def _on_profile_selected(self, name):
        """Handle profile-combo selection change.

        If the current profile has unsaved changes the user is prompted.
        If they cancel, the combo is reverted to the previous profile name
        (signals blocked to avoid recursion).
        """
        if not name: return
        if not self.resolve_unsaved_changes("switch profiles"):
            # Revert the combo to the previously active profile without re-triggering this slot.
            self.profile_combo.blockSignals(True)
            self.profile_combo.setCurrentText(self.current_profile_name)
            self.profile_combo.blockSignals(False)
            return

        self.profile_manager.set_active_profile(name)
        self._load_profile(name)

    def _on_setting_changed(self):
        """Mark the current profile as having pending changes and enable the Save button."""
        self.has_unsaved_changes = True
        self.btn_save.setEnabled(True)

    def _save_current_profile(self, *, show_confirmation: bool = True) -> bool:
        """Persist the current control values to the active profile.

        Args:
            show_confirmation: When ``True`` (default), display a success dialog.
                               Pass ``False`` when called programmatically (e.g. from
                               ``resolve_unsaved_changes``).

        Returns:
            ``True`` if saved successfully, ``False`` if the save was blocked (e.g.
            attempting to modify the read-only "Default Settings" profile).
        """
        if self.current_profile_name == "Default Settings":
            # The default profile is read-only; guard against accidental overwrites.
            if show_confirmation:
                QMessageBox.information(
                    self,
                    "Cannot Modify Default",
                    "The Default Settings profile cannot be modified.\n\nCreate a new profile and save there."
                )
            return False

        mode = self._current_call_number_mode()
        config = {
            "retry_days": self.spin_retry.value(),
            "call_number_mode": mode,
            # Legacy boolean flags kept for backward compatibility with older code paths.
            "collect_lccn": mode in {"lccn", "both"},
            "collect_nlmcn": mode in {"nlmcn", "both"},
            # stop_rule is only meaningful in "both" mode; default to "stop_either" otherwise.
            "stop_rule": self.stop_rule_combo.currentData() if mode == "both" else "stop_either",
        }
        self.profile_manager.save_profile(self.current_profile_name, config)
        self.has_unsaved_changes = False
        self.btn_save.setEnabled(False)
        self.config_changed.emit(config)
        if show_confirmation:
            QMessageBox.information(self, "Saved", f"Profile '{self.current_profile_name}' saved.")
        return True

    def _create_new_profile(self):
        if not self.resolve_unsaved_changes("create a new profile"):
            return

        dialog = CreateProfileDialog(self.profile_manager, self, initial_source="Default Settings")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        name = dialog.profile_name()
        if self.profile_manager.profile_name_exists(name):
            QMessageBox.warning(self, "Duplicate Name", "A profile with that name already exists.")
            return

        source_profile = dialog.source_profile_name()
        source_payload = self.profile_manager.load_profile(source_profile)
        base_settings = self._extract_profile_settings(source_payload).copy()
        new_settings = dialog.profile_settings()
        base_settings.update(new_settings)

        self.profile_manager.save_profile(name, base_settings)
        source_targets = self.profile_manager.get_targets_file(source_profile)
        dest_targets = self.profile_manager.get_targets_file(name)
        dest_targets.parent.mkdir(parents=True, exist_ok=True)
        if source_targets.exists():
            shutil.copy2(source_targets, dest_targets)
        self._refresh_profile_list()
        self.profile_combo.setCurrentText(name) # Will trigger load

    def _delete_current_profile(self):
        """Prompt for confirmation then delete the active profile and fall back to Default Settings."""
        if self.current_profile_name == "Default Settings":
            QMessageBox.warning(self, "Error", "Cannot delete default profile.")
            return
            
        confirm = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete profile '{self.current_profile_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.profile_manager.delete_profile(self.current_profile_name)
            self.profile_manager.set_active_profile("Default Settings")
            self._refresh_profile_list()
            self._load_profile("Default Settings")
            # It will auto-select default or first available

    def list_profile_names(self):
        """Return the list of all saved profile names from ``ProfileManager``."""
        return self.profile_manager.list_profiles()

    def select_profile(self, name: str) -> bool:
        """Switch to *name* by updating the profile combo, including unsaved-changes prompts.

        Args:
            name: Profile name to activate.

        Returns:
            ``True`` if the switch succeeded (the combo now shows *name*), ``False``
            if the profile does not exist or the name is empty.
        """
        if not name:
            return False
        self._refresh_profile_list()
        if name not in self.profile_manager.list_profiles():
            return False
        self.profile_combo.setCurrentText(name)
        return self.current_profile_name == name

    def create_new_profile(self):
        """Open the standard new-profile dialog."""
        self._create_new_profile()

    def get_config(self):
        """Public accessor for other tabs."""
        mode = self._current_call_number_mode()
        return {
            "retry_days": self.spin_retry.value(),
            "call_number_mode": mode,
            # Keep parity with legacy ConfigTab expected keys.
            "collect_lccn": mode in {"lccn", "both"},
            "collect_nlmcn": mode in {"nlmcn", "both"},
            "stop_rule": self.stop_rule_combo.currentData() if mode == "both" else "stop_either",
            "output_tsv": True,
            "output_invalid_isbn_file": True,
        }

    def _current_call_number_mode(self):
        mode = self.call_number_combo.currentData()
        return mode if mode in {"lccn", "nlmcn", "both"} else "lccn"

    def _mode_from_settings(self, settings):
        mode = settings.get("call_number_mode")
        if mode in {"lccn", "nlmcn", "both"}:
            return mode
        collect_lccn = bool(settings.get("collect_lccn", True))
        collect_nlmcn = bool(settings.get("collect_nlmcn", False))
        if collect_lccn and collect_nlmcn:
            return "both"
        if collect_nlmcn:
            return "nlmcn"
        return "lccn"



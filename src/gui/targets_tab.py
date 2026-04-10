"""Target management page — configuring API and Z39.50 harvest sources.

``TargetsTab`` renders the lower half of the Configure page splitter.  It shows
a table of all configured targets with their on/off status, rank, type (API vs
Z39.50), and last-checked connectivity status.  Users can add, edit, remove, and
reorder targets from this page.

Connectivity is checked in a ``ThreadPoolExecutor`` on startup (and on demand)
so the UI stays responsive while Z39.50 socket probes are in flight.

Key design:
- The targets list is persisted by ``TargetsManager`` (in the active profile's
  targets JSON file) and reloaded whenever the profile changes.
- Each table row is backed by a ``Target`` dataclass from ``src.utils.targets_manager``.
- The ``targets_changed`` signal is emitted after every structural change so the
  harvest tab and dashboard can react without polling.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QEvent, QSize
from PyQt6.QtGui import QIcon, QColor
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGroupBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QCheckBox,
    QComboBox,
    QToolButton,
    QInputDialog,
    QDialog,
    QSizePolicy,
)

from src.config.profile_manager import ProfileManager
from src.utils.targets_manager import TargetsManager, Target
from src.z3950.session_manager import validate_connection

from .combo_boxes import ConsistentComboBox
from .icons import get_icon
from .theme_manager import ThemeManager
from .target_dialog import TargetDialog


class TargetsTab(QWidget):
    """Main widget for managing harvest targets (APIs and Z39.50 servers).

    Displays a sortable/selectable table of targets.  Provides buttons to add
    custom Z39.50 targets via ``TargetDialog``, toggle target selection, change
    rank, and test connectivity.

    Signals:
        targets_changed(list): Emitted with the updated list of target dicts
            after any structural change (add/remove/reorder/toggle).
        profile_selected(str): Emitted when the user picks a different profile
            from the profile combo in this tab.
    """

    targets_changed = pyqtSignal(list)
    profile_selected = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._profile_manager = ProfileManager()
        self.before_mutation = None
        active_profile = self._profile_manager.get_active_profile()
        targets_file = self._profile_manager.get_targets_file(active_profile)
        self.manager = TargetsManager(targets_file=targets_file)
        self.server_status = {}  # Cache for server status checks
        self._setup_ui()
        self._check_on_startup()  # Check APIs + active Z3950 on launch

    def _check_on_startup(self):
        """Check APIs and active Z3950 targets on launch."""
        targets = self.manager.get_all_targets()
        api_targets = [
            t for t in targets
            if t.target_type and "api" in t.target_type.lower()
        ]
        z3950_active = [
            t for t in targets
            if not (t.target_type and "api" in t.target_type.lower()) and t.selected
        ]
        check_targets = api_targets + z3950_active
        if check_targets:
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {}
                for t in api_targets:
                    futures[executor.submit(self._check_api_online, t.name)] = t
                for t in z3950_active:
                    futures[executor.submit(validate_connection, t.host, t.port, 2, True)] = t
                for future in as_completed(futures):
                    t = futures[future]
                    try:
                        self.server_status[t.target_id] = future.result()
                    except Exception:
                        self.server_status[t.target_id] = False
        self.refresh_targets()

    def set_advanced_mode(self, enabled):
        """No-op for compatibility with main window calls."""
        _ = enabled

    def load_profile_targets(self, profile_name: str):
        """Switch to the targets file associated with *profile_name*.

        Called automatically when the active profile changes so that
        each profile maintains its own independent set of targets.
        """
        targets_file = self._profile_manager.get_targets_file(profile_name)
        self.manager = TargetsManager(targets_file=targets_file)
        self.server_status.clear()
        self._check_on_startup()

    def eventFilter(self, obj, event):
        """Filter out wheel events on comboboxes to prevent accidental value changes."""
        if isinstance(obj, QComboBox) and event.type() == QEvent.Type.Wheel:
            return True  # Block the event
        return super().eventFilter(obj, event)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(10)

        # Action buttons row
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_add = QPushButton("Add New Target")
        self.btn_add.setObjectName("PrimaryButton")
        self.btn_add.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_add.clicked.connect(self.add_target)

        self.btn_check_servers = QPushButton("Check Servers")
        self.btn_check_servers.setObjectName("SecondaryButton")
        self.btn_check_servers.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_check_servers.clicked.connect(self.check_all_servers)

        self.search_container = QWidget()
        self.search_container.setProperty("class", "SearchContainer")
        search_layout = QHBoxLayout(self.search_container)
        search_layout.setContentsMargins(0, 0, 2, 0)
        search_layout.setSpacing(0)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search targets...")
        self.search_edit.textChanged.connect(self.filter_targets)

        self.search_clear_btn = QToolButton()
        self.search_clear_btn.setText("×")
        self.search_clear_btn.setMinimumSize(24, 24)
        self.search_clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_clear_btn.setToolTip("Clear search")
        self.search_clear_btn.hide()
        self.search_clear_btn.clicked.connect(lambda: self.search_edit.clear())
        self.search_edit.textChanged.connect(lambda t: self.search_clear_btn.setVisible(bool(t)))

        search_layout.addWidget(self.search_edit)
        search_layout.addWidget(self.search_clear_btn)

        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_check_servers)
        btn_layout.addStretch()
        btn_layout.addWidget(self.search_container)

        layout.addLayout(btn_layout)

        # Table
        # --- Table column layout ---
        # Col 0: Rank         — ConsistentComboBox; ResizeToContents (narrow)
        # Col 1: Active       — QPushButton toggle; ResizeToContents (narrow)
        # Col 2: Target Name  — QTableWidgetItem; UserRole stores Target object
        # Col 3: Host / IP    — QTableWidgetItem; Stretch
        # Col 4: Port         — QTableWidgetItem; ResizeToContents (short number)
        # Col 5: Database     — QTableWidgetItem; Stretch
        # Col 6: Edit         — QPushButton (pencil icon); ResizeToContents
        # Col 7: Server       — status pill widget; ResizeToContents
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["Rank", "Active", "Target Name", "Host / IP", "Port", "Database", "Edit", "Server"]
        )
        # Default all columns to Stretch, then pin the narrow utility columns.
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(52)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setAlternatingRowColors(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # Table inherits global stylesheet

        self.table.itemDoubleClicked.connect(lambda item: self._edit_target_from_item(item))

        # Ensure the table always shows a reasonable minimum height
        self.table.setMinimumHeight(200)
        layout.addWidget(self.table)

    def set_profile_options(self, profiles: list, current: str):
        """Compatibility no-op: profile selection lives in the settings card above."""
        return None

    def _emit_targets_changed(self):
        """Emit ``targets_changed`` with the current normalised targets list."""
        self.targets_changed.emit(self.get_targets())

    def _can_mutate_targets(self, action_label: str = "change targets") -> bool:
        """Check whether a structural target mutation is permitted.

        Delegates to the ``before_mutation`` callable injected by
        ``TargetsConfigTab``.  That callable typically prompts the user to save
        or discard unsaved profile settings before the mutation proceeds.

        Args:
            action_label: Short description of the mutation used in any
                          confirmation prompt (e.g. ``"add a target"``).

        Returns:
            ``True`` if the mutation may proceed, ``False`` if blocked.
        """
        if callable(self.before_mutation):
            # before_mutation is injected by TargetsConfigTab to act as a
            # pre-flight check (e.g. unsaved settings guard).
            return bool(self.before_mutation(action_label))
        return True

    @staticmethod
    def _check_api_online(target_name: str) -> bool:
        """Check if a built-in API target is reachable via HTTP.

        Each known API target is mapped to a lightweight probe URL.  A HEAD
        request is tried first; if that fails (some servers reject HEAD) a
        regular GET is attempted as a fallback.  Any HTTP status below 500 is
        treated as "online".

        Args:
            target_name: The display name of the target as stored in the
                         targets JSON file.

        Returns:
            ``True`` if a probe request succeeds, ``False`` otherwise.
        """
        name = target_name.strip().lower()
        # Map each known API target name to a cheap probe URL.
        if "library of congress" in name or name == "loc":
            url = "http://lx2.loc.gov:210/LCDB?operation=explain&version=1.1"
        elif "harvard" in name:
            url = "https://api.lib.harvard.edu/v2/items.json?limit=1"
        elif "openlibrary" in name or "open library" in name:
            url = "https://openlibrary.org/"
        else:
            return False
        try:
            # Prefer HEAD to avoid downloading a response body.
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "LCCNHarvester/0.1")
            with urllib.request.urlopen(req, timeout=4) as resp:
                return resp.status < 500
        except Exception:
            pass
        try:
            # HEAD failed — fall back to a GET request.
            req2 = urllib.request.Request(url)
            req2.add_header("User-Agent", "LCCNHarvester/0.1")
            with urllib.request.urlopen(req2, timeout=4) as resp:
                return resp.status < 500
        except Exception:
            return False

    def check_all_servers(self):
        """Check active Z3950 targets and all API targets in parallel."""
        self.setCursor(Qt.CursorShape.WaitCursor)
        self.server_status.clear()
        targets = self.manager.get_all_targets()

        z3950_active = [
            t for t in targets
            if not (t.target_type and "api" in t.target_type.lower()) and t.selected
        ]
        api_targets = [
            t for t in targets
            if t.target_type and "api" in t.target_type.lower()
        ]

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {}
            for t in z3950_active:
                futures[executor.submit(validate_connection, t.host, t.port, 2, True)] = t
            for t in api_targets:
                futures[executor.submit(self._check_api_online, t.name)] = t

            for future in as_completed(futures):
                t = futures[future]
                try:
                    self.server_status[t.target_id] = future.result()
                except Exception:
                    self.server_status[t.target_id] = False

        self.refresh_targets(check_servers=False)
        self.unsetCursor()

    def refresh_targets(self, check_servers=False):
        """Reload targets from the manager and display them."""
        self.table.clearContents()
        targets = self.manager.get_all_targets()
        self.table.setRowCount(len(targets))
        self.table.blockSignals(True)

        for row, target in enumerate(targets):
            # --- Rank combo (column 0) ---
            # Cap popup height at 12 items so the list doesn't overflow the screen.
            rank_combo = ConsistentComboBox(
                popup_object_name="RankComboPopup",
                max_visible_items=min(len(targets), 12) or 1,
            )
            rank_combo.setMinimumHeight(32)
            # objectName must match the QSS rule QComboBox#RankCombo in styles.py.
            rank_combo.setObjectName("RankCombo")
            for i in range(1, len(targets) + 1):
                rank_combo.addItem(str(i), i)
            # Use findData (by userData int) rather than findText so locale-
            # specific number formatting can never cause a mismatch.
            index = rank_combo.findData(target.rank)
            if index != -1:
                rank_combo.setCurrentIndex(index)
            else:
                # Rank value not in the list (data integrity issue) — put it last.
                rank_combo.setCurrentIndex(rank_combo.count() - 1)
            # Capture both the combo widget and target at the time the lambda is
            # created so the closure doesn't close over a loop variable.
            rank_combo.currentIndexChanged.connect(
                lambda _, t=target, c=rank_combo: self._on_rank_changed(c.currentData(), t)
            )
            rank_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            # eventFilter blocks accidental wheel scrolling (see eventFilter above).
            rank_combo.installEventFilter(self)

            self.table.setCellWidget(row, 0, rank_combo)

            # Active toggle
            active_btn = QPushButton()
            active_btn.setMinimumHeight(32)
            active_btn.setMinimumWidth(50)
            active_btn.setMaximumWidth(90)
            active_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            active_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            active_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            active_btn.setObjectName("ActiveToggle")
            if target.selected:
                active_btn.setProperty("state", "active")
                active_btn.setText("✔")
            else:
                active_btn.setProperty("state", "inactive")
                active_btn.setText("✘")
            active_btn.clicked.connect(lambda checked, t=target: self._toggle_target_active(t))

            self.table.setCellWidget(row, 1, active_btn)

            # --- Target Model Items ---
            name_item = QTableWidgetItem(target.name)
            name_item.setData(Qt.ItemDataRole.UserRole, target)
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, name_item)

            host_item = QTableWidgetItem(target.host)
            host_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, host_item)

            port_str = str(target.port) if target.port else ""
            port_item = QTableWidgetItem(port_str)
            port_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, port_item)

            db_item = QTableWidgetItem(target.database)
            db_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 5, db_item)

            # --- Edit button (column 6) — pencil icon, theme-aware color ---
            if target.target_type == "API":
                blank_item = QTableWidgetItem("")
                blank_item.setFlags(Qt.ItemFlag.NoItemFlags)
                self.table.setItem(row, 6, blank_item)
            else:
                edit_btn = QPushButton()
                edit_btn.setMinimumHeight(32)
                edit_btn.setMinimumWidth(40)
                edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                edit_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                edit_btn.setToolTip("Edit target")
                pencil_svg = (Path(__file__).parent / "icons" / "pencil.svg").read_text(encoding="utf-8")
                pencil_color = "#ffffff" if ThemeManager().get_theme() == "dark" else "#000000"
                edit_btn.setIcon(get_icon(pencil_svg, pencil_color))
                edit_btn.setIconSize(QSize(18, 18))
                edit_btn.setProperty("class", "IconButton")
                edit_btn.clicked.connect(lambda checked, t=target: self._edit_specific_target(t))
                self.table.setCellWidget(row, 6, edit_btn)

            # --- Server status indicator (column 7) ---
            # None = not yet checked; True = online; False = offline.
            is_online = self.server_status.get(target.target_id, None)

            if is_online is None:
                btn_text = "UNKNOWN"
                btn_color = "#6b7280"  # grey — status not yet probed
            elif is_online:
                btn_text = "ONLINE"
                btn_color = "#16a34a"  # green
            else:
                btn_text = "OFFLINE"
                btn_color = "#dc2626"  # red

            server_btn = QPushButton(btn_text)
            server_btn.setMinimumHeight(32)
            server_btn.setMinimumWidth(104)
            server_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            # ForbiddenCursor signals the pill is display-only, not clickable.
            server_btn.setCursor(Qt.CursorShape.ForbiddenCursor)
            # Inline stylesheet applied directly to this instance so the pill
            # colour overrides the global QPushButton rule from styles.py.
            server_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {btn_color};
                    color: #ffffff;
                    border: none;
                    border-radius: 0px;
                    font-weight: bold;
                    font-size: 12px;
                    padding: 0 12px;
                }}
            """)

            server_container = QWidget()
            server_container.setStyleSheet("background: transparent;")
            server_layout = QHBoxLayout(server_container)
            server_layout.setContentsMargins(4, 0, 4, 0)
            server_layout.setSpacing(0)
            server_layout.addWidget(server_btn, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            server_layout.addStretch()
            self.table.setCellWidget(row, 7, server_container)

        self.table.blockSignals(False)
        self._emit_targets_changed()

    def get_targets(self):
        """Return targets formatted for the harvest target factory.

        Normalises the stored ``target_type`` string to either ``"z3950"`` or
        ``"api"`` so downstream code never has to deal with raw type variants.

        Returns:
            A list of dicts with keys: ``target_id``, ``name``, ``type``,
            ``host``, ``port``, ``database``, ``record_syntax``, ``rank``,
            ``selected``.
        """
        mapped_targets = []
        for t in self.manager.get_all_targets():
            target_type = (t.target_type or "").strip().lower()
            # Normalise: any type string containing "z" is treated as Z39.50.
            normalized = "z3950" if "z" in target_type else "api"
            mapped_targets.append(
                {
                    "target_id": t.target_id,
                    "name": t.name,
                    "type": normalized,
                    "host": t.host,
                    "port": t.port,
                    "database": t.database,
                    "record_syntax": t.record_syntax,
                    "rank": t.rank,
                    "selected": t.selected
                }
            )
        return mapped_targets

    def _on_rank_changed(self, new_rank, target):
        """Handle a rank combo-box change and reorder all targets accordingly.

        Implements a splice-and-reassign strategy: the target is removed from
        its current position in the sorted list and re-inserted at the desired
        index, then every target is assigned a clean sequential rank starting
        from 1 to avoid gaps or duplicates.

        Args:
            new_rank: The rank value selected by the user (1-based integer).
            target: The ``Target`` object whose rank was changed.
        """
        if not new_rank or new_rank == target.rank:
            return
        if not self._can_mutate_targets("change target priority"):
            # Pre-flight guard rejected — refresh to restore the original display.
            self.refresh_targets()
            return

        # Sort the full list by current rank so insertion position is predictable.
        all_targets = sorted(
            self.manager.get_all_targets(),
            key=lambda t: t.rank
        )

        # Remove the moved target from the ordered list.
        all_targets = [t for t in all_targets if t.target_id != target.target_id]

        # Clamp the insertion index to valid list bounds.
        new_index = max(0, min(new_rank - 1, len(all_targets)))
        all_targets.insert(new_index, target)

        # Reassign sequential ranks to all targets and persist each change.
        for i, t in enumerate(all_targets, start=1):
            t.rank = i
            self.manager.modify_target(t)

        self.refresh_targets()

    def add_target(self):
        """Open the add-target dialog and persist any new target on acceptance."""
        if not self._can_mutate_targets("add a target"):
            return
        all_targets = self.manager.get_all_targets()
        # Pass the post-add count so the rank spin box includes the new slot.
        total = len(all_targets) + 1
        dialog = TargetDialog(self, total_targets=total)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            chosen_rank = data["rank"]

            new_target = Target(
                target_id="",          # ID assigned by TargetsManager on add
                name=data["name"],
                target_type="Z3950",
                host=data["host"],
                port=data["port"],
                database=data["database"],
                record_syntax="USMARC",
                rank=total,            # temporary end-of-list rank; reordered below
                selected=True,
            )
            self.manager.add_target(new_target)

            # Look up the newly added target by name+host to retrieve its assigned ID.
            added_targets = self.manager.get_all_targets()
            added_target = next((t for t in added_targets if t.name == data["name"] and t.host == data["host"]), None)
            if added_target:
                # Cache the connection test result gathered by the dialog.
                connection_status = dialog.get_connection_status()
                if connection_status is not None:
                    self.server_status[added_target.target_id] = connection_status

                # Move to the rank the user chose; if unchanged, just refresh.
                if chosen_rank != added_target.rank:
                    self._on_rank_changed(chosen_rank, added_target)
                else:
                    self.refresh_targets()
            else:
                self.refresh_targets()

    def edit_target(self):
        """Edit the currently selected table row's target (keyboard/menu entry point)."""
        target = self._get_selected_target()
        if target:
            self._edit_specific_target(target)

    def _edit_specific_target(self, target):
        """Open edit dialog for a given target object."""
        if target.target_type == "API":
            return
        if not self._can_mutate_targets("edit a target"):
            return

        all_targets_now = self.manager.get_all_targets()
        total = len(all_targets_now)
        dialog = TargetDialog(self, target, total_targets=total)
        result = dialog.exec()

        # Remove was clicked inside the dialog
        if dialog.remove_requested:
            self._remove_specific_target(target)
            return

        if result == QDialog.DialogCode.Accepted:
            data = dialog.get_data()

            target.name = data["name"]
            target.host = data["host"]
            target.port = data["port"]
            target.database = data["database"]

            self.manager.modify_target(target)

            # Update server status with the connection test result from dialog
            connection_status = dialog.get_connection_status()
            if connection_status is not None:
                self.server_status[target.target_id] = connection_status

            # Apply rank change if it differs
            chosen_rank = data["rank"]
            if chosen_rank != target.rank:
                self._on_rank_changed(chosen_rank, target)
            else:
                self.refresh_targets()

    def remove_target(self):
        """Remove the currently selected table row's target (keyboard/menu entry point)."""
        target = self._get_selected_target()
        if target:
            self._remove_specific_target(target)

    def _remove_specific_target(self, target):
        """Remove a specific target object."""
        if target.target_type == "API":
            QMessageBox.warning(self, "Restricted", "Cannot remove built-in API targets.")
            return
        if not self._can_mutate_targets("remove a target"):
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to remove '{target.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if confirm == QMessageBox.StandardButton.Yes:
            self.manager.delete_target(target.target_id)
            self.refresh_targets()

    def _toggle_target_active(self, target):
        """Toggle target active status from the table button."""
        if not self._can_mutate_targets("change targets"):
            self.refresh_targets()
            return
        target.selected = not target.selected
        self.manager.modify_target(target)

        # Check server when activating
        if target.selected:
            try:
                if target.target_type and "api" in target.target_type.lower():
                    is_online = self._check_api_online(target.name)
                else:
                    is_online = validate_connection(target.host, target.port, 2, True)
                self.server_status[target.target_id] = is_online
            except Exception:
                is_online = False
                self.server_status[target.target_id] = False

            if not is_online:
                if target.target_type and "api" in target.target_type.lower():
                    address = target.name
                else:
                    address = f"{target.host}:{target.port}/{target.database}" if target.database else f"{target.host}:{target.port}"
                QMessageBox.warning(
                    self,
                    "Connection Failed",
                    f"Could not connect to {address}.\nThe target has been activated but may not respond during harvest.",
                )

        self.refresh_targets()

    def _edit_target_from_item(self, item):
        """Edit the target corresponding to the double-clicked table item."""
        row = item.row()
        name_item = self.table.item(row, 2)  # Name column
        if name_item:
            target = name_item.data(Qt.ItemDataRole.UserRole)
            if target:
                self._edit_specific_target(target)

    def _get_selected_target(self):
        """Return the ``Target`` object for the currently selected row, or ``None``.

        The ``Target`` object is stored in column 2 (Target Name) via
        ``Qt.ItemDataRole.UserRole`` so it can be retrieved without maintaining a
        separate row-to-target mapping.
        """
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 2)  # Target Name column carries the UserRole data
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None
    def filter_targets(self, text):
        """Filter rows based on search text (Target Name only)."""
        text = text.lower()
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 2)  # Name column reverted to index 2
            name = name_item.text().lower() if name_item else ""
            visible = text in name
            self.table.setRowHidden(row, not visible)



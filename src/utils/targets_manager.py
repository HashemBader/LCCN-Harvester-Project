"""
targets_manager.py

Persistence layer for harvest target configuration (Z39.50 servers and APIs).

Responsibilities
----------------
- Define the :class:`Target` data class, which holds all connection details
  for a single harvest source (name, type, host, port, database, credentials,
  rank, and enabled/disabled flag).
- Provide :class:`TargetsManager`, which reads from and writes to a
  tab-separated values (TSV) file at ``data/targets.tsv``.
- Ensure the three built-in API targets (LoC, Harvard, OpenLibrary) are
  always present, adding them to any existing file that is missing them.

Storage format
--------------
The TSV file has a header row followed by one target per data row:

    target_id  name  target_type  host  port  database  record_syntax  rank  selected  username  password

- ``port`` is stored as an integer or left empty for API targets.
- ``selected`` is stored as the literal string ``"True"`` or ``"False"``.
- Rows are always written in ascending ``rank`` order.

Z39.50 connection testing
--------------------------
The :meth:`TargetsManager.test_target_connection` method delegates to
:func:`src.z3950.session_manager.validate_connection` when the z3950 module
is available.  If the module is not installed, a no-op stub is used so the
rest of the application continues to work.
"""

import csv
import os
from dataclasses import dataclass
from typing import List, Optional
from src.utils.messages import ConfigMessages

# Constants defining the storage location
DATA_DIR = "data"
TARGETS_FILE = os.path.join(DATA_DIR, "targets.tsv")

try:
    from src.z3950.session_manager import validate_connection
except ImportError:
    # z3950 is an optional dependency; provide a no-op stub so the rest of the
    # application works without it.  The test_target_connection method will
    # always return False in this case.
    def validate_connection(host, port, timeout=5):
        return False


@dataclass
class Target:
    """
    Data class representing a single harvest source (Z39.50 server or API).

    Fields that are marked "Z39.50 only" are left as empty strings or
    ``None`` for API targets; they are stored as empty columns in the TSV.

    Attributes
    ----------
    target_id : str
        Unique numeric identifier (stored as a string for TSV compatibility).
    name : str
        Human-readable display name shown in the GUI targets list.
    target_type : str
        Either ``"Z3950"`` (Z39.50 server) or ``"API"`` (REST/HTTP endpoint).
    host : str
        Hostname or IP address for Z39.50 connections.  Empty for API targets.
    port : int | None
        TCP port for Z39.50 connections.  ``None`` for API targets.
    database : str
        Z39.50 database name (e.g., ``"LCDB"`` for the LoC).  Empty for APIs.
    record_syntax : str
        Requested Z39.50 record syntax, e.g. ``"USMARC"`` or ``"UNIMARC"``.
        Empty for API targets.
    rank : int
        Execution priority — targets are tried in ascending rank order.
        Lower numbers are queried first.
    selected : bool
        Whether this target is currently active / enabled for harvesting.
    username : str
        Optional authentication username (Z39.50 targets that require login).
    password : str
        Optional authentication password.  Stored in plaintext in the TSV.
    """
    target_id: str
    name: str
    target_type: str          # "Z3950" or "API"
    host: str                 # Host-name or IP (Z39.50 only)
    port: Optional[int]       # Port number (Z39.50 only)
    database: str             # Database name (Z39.50 only)
    record_syntax: str        # e.g. USMARC, UNIMARC (Z39.50 only)
    rank: int                 # Execution order (lower number = higher priority)
    selected: bool            # Whether this target is currently active
    username: str = ""        # Username for target authentication
    password: str = ""        # Password for target authentication

class TargetsManager:
    """
    CRUD manager for the targets TSV configuration file.

    On construction the manager guarantees the storage file and its parent
    directory exist, and that the three built-in API targets (LoC, Harvard,
    OpenLibrary) are present.  All public methods re-read the file before
    modifying it so that concurrent GUI/CLI usage stays consistent.
    """

    def __init__(self, targets_file=None):
        """
        Initialise the TargetsManager and ensure the data file exists.

        Parameters
        ----------
        targets_file : str | Path | None
            Path to the TSV file.  Defaults to ``data/targets.tsv`` relative
            to the current working directory when ``None``.
        """
        self._targets_file = str(targets_file) if targets_file is not None else TARGETS_FILE
        self._ensure_targets_file()
        self._ensure_default_api_targets()

    def _ensure_targets_file(self):
        """
        Check if the data directory and targets file exist.
        If not, create them and populate the file with default starting targets.
        """
        # Create the parent directory if it doesn't exist
        parent_dir = os.path.dirname(self._targets_file)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        # Create targets file with defaults if it doesn't exist
        if not os.path.exists(self._targets_file):
            default_targets = [
                Target(
                    target_id="1",
                    name="Library of Congress API",
                    target_type="API",
                    host="",
                    port=None,
                    database="",
                    record_syntax="",
                    rank=1,
                    selected=True,
                    username="",
                    password=""
                ),
                Target(
                    target_id="2",
                    name="Harvard Library API",
                    target_type="API",
                    host="",
                    port=None,
                    database="",
                    record_syntax="",
                    rank=2,
                    selected=True,
                    username="",
                    password=""
                ),
                Target(
                    target_id="3",
                    name="OpenLibrary API",
                    target_type="API",
                    host="",
                    port=None,
                    database="",
                    record_syntax="",
                    rank=3,
                    selected=True,
                    username="",
                    password=""
                )
            ]
            self.save_targets(default_targets)

    def _ensure_default_api_targets(self):
        """
        Ensure all three core API targets are present in an existing TSV file.

        Called after :meth:`_ensure_targets_file` so the file already exists.
        Compares existing target names (case-insensitively) against the three
        required names and appends any that are missing, assigning them IDs
        and ranks that are one higher than the current maximum to avoid
        collisions.
        """
        targets = self.get_all_targets()
        if not targets:
            return

        # Build a lowercase set for case-insensitive membership testing.
        existing_names = {t.name.strip().lower() for t in targets}
        # Append missing targets at ranks after the highest existing rank.
        next_rank = max((t.rank for t in targets), default=0) + 1

        defaults = [
            "Library of Congress API",
            "Harvard Library API",
            "OpenLibrary API",
        ]
        missing = [name for name in defaults if name.lower() not in existing_names]
        if not missing:
            return

        # Compute the next available numeric ID from existing targets.
        next_id = (
            max(
                (int(t.target_id) for t in targets if str(t.target_id).isdigit()),
                default=0,
            )
            + 1
        )
        for name in missing:
            targets.append(
                Target(
                    target_id=str(next_id),
                    name=name,
                    target_type="API",
                    host="",
                    port=None,
                    database="",
                    record_syntax="",
                    rank=next_rank,
                    selected=True,
                    username="",
                    password="",
                )
            )
            next_id += 1
            next_rank += 1

        self.save_targets(targets)


    def get_all_targets(self) -> List[Target]:
        """
        Read all targets from the TSV file and return them sorted by rank.

        Returns an empty list (without raising) if the file does not yet
        exist or if a parsing error occurs; errors are printed to stdout.

        Returns
        -------
        List[Target]
            Target objects in ascending rank order.
        """
        targets: List[Target] = []
        if not os.path.exists(self._targets_file):
            return targets

        try:
            with open(self._targets_file, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter="\t")
                for row in reader:
                    # Port is an integer for Z39.50 targets; empty for API targets.
                    port_val = row.get("port", "").strip()
                    port_int = int(port_val) if port_val else None

                    # The "selected" column is serialised as the string "True"/"False".
                    selected_val = row.get("selected", "False")
                    is_selected = (selected_val.lower() == "true")

                    targets.append(
                        Target(
                            target_id=row["target_id"],
                            name=row["name"],
                            target_type=row["target_type"],
                            host=row["host"],
                            port=port_int,
                            database=row["database"],
                            record_syntax=row["record_syntax"],
                            # Default rank to 0 for rows that pre-date the rank column.
                            rank=int(row["rank"]) if row.get("rank") else 0,
                            selected=is_selected,
                            username=row.get("username", ""),
                            password=row.get("password", "")
                        )
                    )
        except Exception as e:
            print(ConfigMessages.load_error.format(error=e))

        # Ensure callers always receive targets in priority order.
        targets.sort(key=lambda x: x.rank)
        return targets

    def save_targets(self, targets: List[Target]):
        """
        Write the complete list of Target objects to the TSV file (full overwrite).

        The file is always written in ascending rank order so that
        :meth:`get_all_targets` returns a consistently ordered list without
        needing to sort after every individual change.

        Parameters
        ----------
        targets : List[Target]
            The full list of targets to persist.  This replaces whatever is
            currently in the file.
        """
        try:
            # Enforce rank ordering on write so the file on disk is human-readable.
            targets.sort(key=lambda x: x.rank)

            with open(self._targets_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter="\t")
                # Header row matches the column order expected by get_all_targets.
                writer.writerow([
                    "target_id", "name", "target_type", "host", "port",
                    "database", "record_syntax", "rank", "selected", "username", "password"
                ])

                for t in targets:
                    writer.writerow([
                        t.target_id,
                        t.name,
                        t.target_type,
                        t.host,
                        # Write port as an integer, or an empty string for API targets.
                        t.port if t.port is not None else "",
                        t.database,
                        t.record_syntax,
                        t.rank,
                        str(t.selected),  # Serialise Python bool to "True" / "False"
                        t.username,
                        t.password
                    ])
        except Exception as e:
            print(ConfigMessages.save_error.format(error=e))

    def add_target(self, target: Target):
        """
        Append a new target to the configuration and persist the change.

        If ``target.target_id`` is falsy (empty string or ``None``), a new
        ID is generated by finding the current maximum integer ID and
        incrementing it by one.

        Parameters
        ----------
        target : Target
            The new target to add.  Its ``target_id`` may be left empty for
            auto-assignment.
        """
        targets = self.get_all_targets()

        if not target.target_id:
            # Find the highest existing numeric ID and add 1.
            max_id = 0
            for t in targets:
                try:
                    tid = int(t.target_id)
                    if tid > max_id:
                        max_id = tid
                except ValueError:
                    pass  # Non-numeric IDs are ignored in the max calculation.
            target.target_id = str(max_id + 1)

        targets.append(target)
        self.save_targets(targets)
        print(ConfigMessages.target_added.format(name=target.name))

    def modify_target(self, updated_target: Target):
        """
        Replace an existing target in-place, identified by ``target_id``.

        Performs a linear scan for the matching ID and replaces that slot in
        the list before re-saving.  If no matching target is found, prints
        a not-found message without modifying the file.

        Parameters
        ----------
        updated_target : Target
            A Target object with the same ``target_id`` as the one to update
            and the desired new field values.
        """
        targets = self.get_all_targets()
        found = False
        for i, t in enumerate(targets):
            if t.target_id == updated_target.target_id:
                targets[i] = updated_target
                found = True
                break

        if found:
            self.save_targets(targets)
            print(ConfigMessages.target_modified.format(name=updated_target.name))
        else:
            print(ConfigMessages.target_not_found.format(target_id=updated_target.target_id))

    def delete_target(self, target_id: str):
        """
        Remove a target by ID and re-sequence the remaining ranks.

        After deletion the surviving targets are renumbered 1..N in their
        current order (which is already rank-sorted because
        :meth:`get_all_targets` sorts on read).  This keeps ranks
        contiguous and avoids gaps that could confuse the GUI ordering.

        Parameters
        ----------
        target_id : str
            The ``target_id`` of the target to remove.
        """
        targets = self.get_all_targets()
        original_count = len(targets)

        # Build the list without the deleted target.
        remaining_targets = [t for t in targets if t.target_id != target_id]

        if len(remaining_targets) < original_count:
            # Re-assign ranks starting at 1 to close any gap left by the deletion.
            # get_all_targets already sorted by rank, so the relative order is preserved.
            for i, target in enumerate(remaining_targets):
                target.rank = i + 1

            self.save_targets(remaining_targets)
            print(ConfigMessages.target_deleted.format(target_id=target_id))
        else:
            print(ConfigMessages.target_not_found.format(target_id=target_id))

    def test_target_connection(self, host: str, port: int) -> bool:
        """
        Test a TCP/Z39.50 connection to the given host and port.

        Delegates to :func:`src.z3950.session_manager.validate_connection`
        when the z3950 module is available.  If the module is not installed,
        the stub always returns ``False``.

        Parameters
        ----------
        host : str
            Hostname or IP address of the Z39.50 server.
        port : int
            TCP port number (standard Z39.50 port is 210).

        Returns
        -------
        bool
            ``True`` if a connection could be established; ``False`` otherwise.
        """
        return validate_connection(host, port)


"""
Module: targets_manager.py
Purpose: Manage Z39.50 targets and configuration.

This module handles the persistence and retrieval of connection details for
Z39.50 servers and APIs. It reads from and writes to a TSV (Tab-Separated Values)
file located in the data directory.
"""

import csv
import os
from dataclasses import dataclass, asdict
from typing import List, Optional
from utils.messages import ConfigMessages

# Constants defining the storage location
DATA_DIR = "data"
TARGETS_FILE = os.path.join(DATA_DIR, "targets.tsv")

try:
    from z3950.session_manager import validate_connection
except ImportError:
    # Fallback or mock if z3950 module is not available in some contexts
    def validate_connection(host, port, timeout=5):
        return False


@dataclass
class Target:
    """
    Data class representing a single connection target (Library or API).
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
    username: str = ""        # Authentication username (optional)
    password: str = ""        # Authentication password (optional)

class TargetsManager:
    """
    Manager class for handling configuration file operations (CRUD).
    """
    def __init__(self):
        """Initialize the TargetsManager and ensure the data file exists."""
        self._ensure_targets_file()

    def _ensure_targets_file(self):
        """
        Check if the data directory and targets file exist.
        If not, create them and populate the file with default starting targets.
        """
        # Create 'data' directory if it doesn't exist
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)

        # Create 'targets.tsv' with defaults if it doesn't exist
        if not os.path.exists(TARGETS_FILE):
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
                    selected=True
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
                    selected=True
                )
            ]
            self.save_targets(default_targets)


    def get_all_targets(self) -> List[Target]:
        """
        Read all targets from the TSV file.
        
        Returns:
            List[Target]: A list of Target objects sorted by rank.
        """
        targets: List[Target] = []
        if not os.path.exists(TARGETS_FILE):
             return targets

        try:
            with open(TARGETS_FILE, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter="\t")
                for row in reader:
                    # Handle potential missing or empty port (convert string to int or None)
                    port_val = row.get("port", "").strip()
                    port_int = int(port_val) if port_val else None
                    
                    # Handle 'selected' boolean (CSV stores as "True"/"False")
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
                            rank=int(row["rank"]) if row.get("rank") else 0,
                            selected=is_selected,
                            username=row.get("username", ""),
                            password=row.get("password", "")
                        )
                    )
        except Exception as e:
            print(ConfigMessages.load_error.format(error=e))
        
        # Sort targets by their rank attribute (ascending)
        targets.sort(key=lambda x: x.rank)
        return targets

    def save_targets(self, targets: List[Target]):
        """
        Write the list of Target objects back to the TSV file.
        
        Args:
            targets (List[Target]): The list of targets to save.
        """
        try:
            # Always save in rank order
            targets.sort(key=lambda x: x.rank)
            
            with open(TARGETS_FILE, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter="\t")
                # Write header row
                writer.writerow([
                    "target_id", "name", "target_type", "host", "port", 
                    "database", "record_syntax", "rank", "selected", 
                    "username", "password"
                ])

                # Write data rows
                for t in targets:
                    writer.writerow([
                        t.target_id,
                        t.name,
                        t.target_type,
                        t.host,
                        t.port if t.port is not None else "",
                        t.database,
                        t.record_syntax,
                        t.rank,
                        str(t.selected), # Serialize boolean to "True" or "False"
                        t.username,
                        t.password
                    ])
        except Exception as e:
            print(ConfigMessages.save_error.format(error=e))

    def add_target(self, target: Target):
        """
        Add a new target to the configuration.
        Auto-generates a unique target_id if one is not provided.
        """
        targets = self.get_all_targets()
        
        # Auto-increment ID generation if ID is missing
        if not target.target_id:
            max_id = 0
            for t in targets:
                try:
                    tid = int(t.target_id)
                    if tid > max_id: max_id = tid
                except ValueError:
                    pass
            target.target_id = str(max_id + 1)
            
        targets.append(target)
        self.save_targets(targets)
        print(ConfigMessages.target_added.format(name=target.name))

    def modify_target(self, updated_target: Target):
        """
        Update an existing target's details based on its target_id.
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
        Remove a target from the configuration by its ID.
        Re-sequences the ranks of remaining targets to ensure they are continuous.
        """
        targets = self.get_all_targets()
        original_count = len(targets)
        # Filter out the target with the matching ID
        remaining_targets = [t for t in targets if t.target_id != target_id]
        
        if len(remaining_targets) < original_count:
            # Re-sequence ranks
            # Since get_all_targets sorts by rank, remaining_targets should still be roughly in order.
            # We enforce 1..N order.
            for i, target in enumerate(remaining_targets):
                target.rank = i + 1
            
            self.save_targets(remaining_targets)
            print(ConfigMessages.target_deleted.format(target_id=target_id))
        else:
            print(ConfigMessages.target_not_found.format(target_id=target_id))

    def test_target_connection(self, host: str, port: int) -> bool:
        """
        Test connection to a Z39.50 target.
        
        Args:
            host (str): Hostname or IP
            port (int): Port number
            
        Returns:
            bool: True if connection successful
        """
        return validate_connection(host, port)




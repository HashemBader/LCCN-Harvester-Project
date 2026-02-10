"""
Module: targets.py
Harvest target implementations that conform to the HarvestTarget protocol.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from harvester.orchestrator import TargetResult
from utils import messages

logger = logging.getLogger(__name__)

# Z3950 availability - will be checked lazily when needed
# Don't import at module level to avoid crash if PyZ3950 has compatibility issues
Z3950_AVAILABLE = None
Z3950Client = None


class Z3950Target:
    """Z39.50 target implementation."""

    def __init__(self, name: str, host: str, port: int, database: str):
        self.name = name
        self.host = host
        self.port = port
        self.database = database

    def lookup(self, isbn: str) -> TargetResult:
        """Lookup ISBN using Z39.50."""
        # Lazy import Z3950Client to avoid crash if PyZ3950 has issues
        global Z3950_AVAILABLE, Z3950Client
        if Z3950_AVAILABLE is None:
            try:
                from z3950.client import Z3950Client as Z3950ClientClass
                Z3950Client = Z3950ClientClass
                Z3950_AVAILABLE = True
            except Exception as e:
                Z3950_AVAILABLE = False
                logger.warning(messages.NetworkMessages.z3950_not_available_detail.format(error=str(e)))

        if not Z3950_AVAILABLE:
            return TargetResult(
                success=False,
                source=self.name,
                error=messages.NetworkMessages.z3950_unavailable
            )

        try:
            with Z3950Client(self.host, self.port, self.database) as client:
                records = client.search_by_isbn(isbn)

                if not records:
                    return TargetResult(
                        success=False,
                        source=self.name,
                        error=messages.NetworkMessages.no_match.format(target=self.name)
                    )

                # Extract LCCN from first record
                record = records[0]
                lccn = None
                nlmcn = None

                # Try to get LCCN from field 010$a
                if record['010']:
                    lccn_field = record['010']['a']
                    if lccn_field:
                        lccn = lccn_field.strip()

                # Try to get NLM from field 060$a (if it exists)
                if record['060']:
                    nlm_field = record['060']['a']
                    if nlm_field:
                        nlmcn = nlm_field.strip()

                if lccn:
                    return TargetResult(
                        success=True,
                        lccn=lccn,
                        nlmcn=nlmcn,
                        source=self.name
                    )
                else:
                    return TargetResult(
                        success=False,
                        source=self.name,
                        error=messages.NetworkMessages.record_no_lccn
                    )

        except Exception as e:
            logger.error(messages.NetworkMessages.z3950_lookup_failed.format(
                isbn=isbn, target=self.name, error=str(e)
            ))
            return TargetResult(
                success=False,
                source=self.name,
                error=str(e)
            )


class APITarget:
    """
    Placeholder API target.
    Will be replaced with real API implementations.
    """

    def __init__(self, name: str):
        self.name = name

    def lookup(self, isbn: str) -> TargetResult:
        """Placeholder API lookup."""
        # TODO: Implement real API lookups
        return TargetResult(
            success=False,
            source=self.name,
            error=messages.NetworkMessages.api_not_implemented
        )


def create_target_from_config(target_config: dict):
    """
    Create a target instance from GUI configuration.

    Args:
        target_config: Dictionary with target configuration
            Example: {"name": "Yale", "type": "z3950", "host": "...", "port": 210, "database": "..."}

    Returns:
        Target instance that implements HarvestTarget protocol
    """
    target_type = target_config.get("type", "api")
    name = target_config.get("name", "Unknown")

    if target_type == "z3950":
        return Z3950Target(
            name=name,
            host=target_config.get("host", ""),
            port=target_config.get("port", 210),
            database=target_config.get("database", "")
        )
    elif target_type == "api":
        return APITarget(name=name)
    else:
        raise ValueError(f"Unknown target type: {target_type}")

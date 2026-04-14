import sys
from types import SimpleNamespace

import src.database as src_database

sys.modules.setdefault("database", src_database)

from src.gui.dashboard import DashboardTab
from src.gui.harvest_support import HarvestWorker


class _WorkerState:
    def __init__(self, *, db_only=False):
        self.config = {"db_only": db_only}
        self.run_stats = object()


def test_dashboard_normalises_db_only_local_catalog_misses():
    stats = DashboardTab._normalise_run_stats(
        {
            "found": 2,
            "cached": 3,
            "failed": 1,
            "skipped": 4,
            "invalid": 5,
            "not_in_local_catalog": 6,
        }
    )

    assert stats == {
        "processed": 16,
        "successful": 5,
        "failed": 11,
        "invalid": 5,
    }


def test_db_only_worker_ignores_selected_targets_for_cache_reads():
    worker = _WorkerState(db_only=True)

    assert HarvestWorker._effective_targets_for_run(worker, [{"name": "LoC"}]) == []


def test_worker_final_stats_include_local_catalog_misses():
    worker = _WorkerState()
    summary = SimpleNamespace(
        total_isbns=9,
        successes=2,
        failures=1,
        cached_hits=3,
        skipped_recent_fail=4,
        not_in_local_catalog=5,
    )

    stats = HarvestWorker._build_final_stats(worker, summary, 6)

    assert stats == {
        "total": 9,
        "found": 2,
        "failed": 6,
        "cached": 3,
        "skipped": 4,
        "invalid": 6,
        "not_in_local_catalog": 5,
        "run_stats": worker.run_stats,
    }

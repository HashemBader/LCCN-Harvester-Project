import sys
from unittest.mock import MagicMock
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.harvester.orchestrator import HarvestOrchestrator, HarvestTarget, TargetResult
from src.database import DatabaseManager

class MockTarget:
    def __init__(self, name, success=False, error=None):
        self.name = name
        self.should_succeed = success
        self.error_msg = error

    def lookup(self, isbn):
        if self.should_succeed:
            return TargetResult(success=True, lccn="123", source=self.name)
        return TargetResult(success=False, error=self.error_msg)

def test_callbacks():
    print("Verifying HarvestOrchestrator callbacks...")
    
    # Setup
    db = MagicMock(spec=DatabaseManager)
    db.get_main.return_value = None # No cache
    db.should_skip_retry.return_value = False
    
    events = []
    def progress_cb(event, payload):
        events.append((event, payload))

    # Test Case 1: Target Failure then Success
    target1 = MockTarget("Target1", success=False, error="Connection failed")
    target2 = MockTarget("Target2", success=True)
    
    orch = HarvestOrchestrator(
        db=db,
        targets=[target1, target2],
        progress_cb=progress_cb,
        batch_size=1
    )

    print("Running orch.run for '9781234567890'...")
    orch.run(["9781234567890"], dry_run=True)

    # Verification
    expected_sequence = [
        "isbn_start",
        "target_start", # Target1
        "target_start", # Target2
        "success",      # Target2
        "stats"         # Running stats
    ]
    
    actual_sequence = [e[0] for e in events]
    
    # Check basic sequence
    assert actual_sequence == expected_sequence, f"Expected {expected_sequence}, got {actual_sequence}"
    
    # Check payloads
    assert events[1][1]["target"] == "Target1"
    assert events[2][1]["target"] == "Target2"
    assert events[3][1]["target"] == "Target2"
    
    assert events[3][1]["target"] == "Target2"
    
    # Check stats event
    # Orchestrator emits stats after each ISBN processing
    # With batch_size=1, flush() might also happen, but stats are emitted before flushing logic inside the loop
    # Let's find the last 'stats' event
    stats_events = [e for e in events if e[0] == "stats"]
    assert len(stats_events) > 0, "No stats event emitted"
    last_stats = stats_events[-1][1]
    assert last_stats["successes"] == 1
    assert last_stats["failures"] == 0
    assert last_stats["total"] == 1
    
    print("[OK] Callback sequence verified: Start -> Target1(Fail) -> Target2(Success) + Stats")

    # Test Case 2: Cache Hit
    events.clear()
    db.get_main.return_value = "CachedRecord"
    
    print("Running orch.run for 'cached-isbn'...")
    orch.run(["cached-isbn"], dry_run=True)
    
    assert events[0][0] == "isbn_start"
    assert events[1][0] == "cached"
    
    print("[OK] Cache hit callback verified.")
    print("All callback verifications passed!")

if __name__ == "__main__":
    test_callbacks()

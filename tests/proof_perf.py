import time
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.harvester.orchestrator import HarvestOrchestrator, TargetResult
from src.database import DatabaseManager

@dataclass
class MockSlowTarget:
    name: str = "SlowTarget"
    delay: float = 0.1  # 100ms delay

    def lookup(self, isbn: str) -> TargetResult:
        time.sleep(self.delay)
        return TargetResult(success=True, lccn="simulated", source=self.name)

def run_benchmark():
    db_path = "data/bench_test.sqlite3"
    # cleanup
    Path(db_path).unlink(missing_ok=True)
    
    db = DatabaseManager(db_path)
    db.init_db()

    # Create 20 ISBNs
    isbns = [f"97800000000{i}" for i in range(20)]
    
    print(f"Benchmarking with {len(isbns)} items and 0.1s target delay...")

    # Case 1: Sequential (max_workers=1)
    print("\nRunning Sequential (max_workers=1)...")
    orch_seq = HarvestOrchestrator(
        db=db,
        targets=[MockSlowTarget()],
        max_workers=1,
        batch_size=10
    )
    start_seq = time.time()
    orch_seq.run(isbns, dry_run=True)
    dur_seq = time.time() - start_seq
    print(f"Sequential duration: {dur_seq:.2f}s")

    # Case 2: Parallel (max_workers=4)
    print("\nRunning Parallel (max_workers=4)...")
    orch_par = HarvestOrchestrator(
        db=db,
        targets=[MockSlowTarget()],
        max_workers=4,
        batch_size=10
    )
    start_par = time.time()
    orch_par.run(isbns, dry_run=True)
    dur_par = time.time() - start_par
    print(f"Parallel duration: {dur_par:.2f}s")

    speedup = dur_seq / dur_par
    print(f"\nSpeedup: {speedup:.2f}x")
    
    if speedup > 2.0:
        print("[PASS] Significant speedup detected.")
    else:
        print("[FAIL] Speedup insufficient (threading might not be working).")

if __name__ == "__main__":
    run_benchmark()

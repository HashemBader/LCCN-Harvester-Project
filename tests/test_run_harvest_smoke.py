from pathlib import Path
from src.harvester.run_harvest import run_harvest

def test_run_harvest_smoke(tmp_path: Path):
    tsv = tmp_path / "isbns.tsv"
    tsv.write_text("isbn\n9780132350884\n0000000000\n", encoding="utf-8")

    summary = run_harvest(tsv, dry_run=True)
    assert summary.total_isbns == 2

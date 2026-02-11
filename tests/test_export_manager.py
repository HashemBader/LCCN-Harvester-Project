
import csv
import pytest
from pathlib import Path
from src.database.db_manager import DatabaseManager, MainRecord, AttemptedRecord
from src.harvester.export_manager import ExportManager

@pytest.fixture
def populated_db(tmp_path):
    db_path = tmp_path / "test.sqlite3"
    db = DatabaseManager(db_path)
    db.init_db()
    
    # Insert main records
    db.upsert_main(MainRecord(isbn="111", lccn="A1", nlmcn="N1", classification="A", source="LoC", date_added="2023-01-01"))
    db.upsert_main(MainRecord(isbn="222", lccn="B2", nlmcn="N2", classification="B", source="Harvard", date_added="2023-01-02"))
    
    # Insert attempted records
    db.upsert_attempted(isbn="333", last_target="LoC", last_error="Err1", attempted_time="2023-01-03")
    
    return db_path

def test_export_main_tsv(tmp_path, populated_db):
    manager = ExportManager(populated_db)
    output_path = tmp_path / "output.tsv"
    
    config = {
        "source": "main",
        "format": "tsv",
        "columns": ["ISBN", "LCCN"],
        "output_path": str(output_path),
        "include_header": True
    }
    
    result = manager.export(config)
    assert result["success"]
    assert output_path.exists()
    
    with open(output_path, "r", encoding="utf-8") as f:
        content = f.read().strip().split("\n")
        assert len(content) == 3 # Header + 2 rows
        assert content[0] == "ISBN\tLCCN"
        # Order is by ISBN
        assert "111\tA1" in content[1]
        assert "222\tB2" in content[2]

def test_export_attempted(tmp_path, populated_db):
    manager = ExportManager(populated_db)
    output_path = tmp_path / "output.tsv"
    
    config = {
        "source": "attempted",
        "format": "tsv",
        "columns": [], # Attempted ignores selected columns currently
        "output_path": str(output_path),
        "include_header": True
    }
    
    result = manager.export(config)
    assert result["success"]
    assert output_path.exists()
    
    with open(output_path, "r", encoding="utf-8") as f:
        content = f.read()
        assert "333" in content
        assert "Err1" in content

def test_export_both(tmp_path, populated_db):
    manager = ExportManager(populated_db)
    output_path = tmp_path / "output.tsv"
    
    config = {
        "source": "both",
        "format": "tsv",
        "columns": ["ISBN"],
        "output_path": str(output_path),
        "include_header": True
    }
    
    result = manager.export(config)
    assert result["success"]
    
    # Expect output_success.tsv and output_failed.tsv
    success_path = tmp_path / "output_success.tsv"
    failed_path = tmp_path / "output_failed.tsv"
    
    assert success_path.exists()
    assert failed_path.exists()


def test_export_main_csv(tmp_path, populated_db):
    manager = ExportManager(populated_db)
    output_path = tmp_path / "output.csv"

    config = {
        "source": "main",
        "format": "csv",
        "columns": ["ISBN", "LCCN"],
        "output_path": str(output_path),
        "include_header": True
    }

    result = manager.export(config)
    assert result["success"]
    assert output_path.exists()

    with open(output_path, "r", encoding="utf-8") as f:
        rows = f.read().strip().split("\n")
        assert rows[0] == "ISBN,LCCN"
        assert "111,A1" in rows[1]


def test_export_main_json(tmp_path, populated_db):
    manager = ExportManager(populated_db)
    output_path = tmp_path / "output.json"

    config = {
        "source": "main",
        "format": "json",
        "columns": ["ISBN", "LCCN"],
        "output_path": str(output_path),
        "include_header": True
    }

    result = manager.export(config)
    assert result["success"]
    assert output_path.exists()

    import json
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert data[0]["ISBN"] == "111"
    assert data[0]["LCCN"] == "A1"

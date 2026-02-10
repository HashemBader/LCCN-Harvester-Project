import sqlite3
from pathlib import Path

db_path = Path("data/lccn_harvester.sqlite3")

print(f"Checking DB at: {db_path.absolute()}")
if not db_path.exists():
    print("FATAL: Database file does not exist!")
else:
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # Check Main
        rows_main = conn.execute("SELECT COUNT(*) FROM main").fetchone()[0]
        print(f"Rows in 'main' (Success): {rows_main}")
        
        # Check Attempted
        rows_att = conn.execute("SELECT COUNT(*) FROM attempted").fetchone()[0]
        print(f"Rows in 'attempted' (Failures): {rows_att}")
        
        # Sample data
        if rows_main > 0:
            print("\nSample Main:")
            for r in conn.execute("SELECT * FROM main LIMIT 3"):
                print(dict(r))
                
        if rows_att > 0:
            print("\nSample Attempted:")
            for r in conn.execute("SELECT * FROM attempted LIMIT 3"):
                print(dict(r))
                
    except Exception as e:
        print(f"Error reading DB: {e}")

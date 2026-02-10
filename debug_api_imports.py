import sys
from pathlib import Path

# Setup path like run_harvest
root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

print(f"Path[0]: {sys.path[0]}")

print("Attempting to import src.api.base_api...")
try:
    from src.api import base_api
    print("SUCCESS: src.api.base_api")
except Exception as e:
    print(f"FAILED: src.api.base_api -> {e}")

print("Attempting to import src.api.loc_api...")
try:
    from src.api import loc_api
    print("SUCCESS: src.api.loc_api")
except Exception as e:
    print(f"FAILED: src.api.loc_api -> {e}")
    import traceback
    traceback.print_exc()

print("Attempting to import src.api.harvard_api...")
try:
    from src.api import harvard_api
    print("SUCCESS: src.api.harvard_api")
except Exception as e:
    print(f"FAILED: src.api.harvard_api -> {e}")
    import traceback
    traceback.print_exc()

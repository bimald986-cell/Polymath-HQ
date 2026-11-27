import sys
from pathlib import Path

# build_tracker.py lives one directory up; make it importable without packaging.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

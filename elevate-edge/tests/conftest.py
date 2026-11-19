"""Test setup for the Elevate Edge app.

The app is a module, not a package, so `elevate-edge/` goes on sys.path. The
secret-key and dev switches are set here because the module builds the app on
import; the tests that must see them *missing* clear them again explicitly.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["ELEVATE_DEV"] = "1"
os.environ["ELEVATE_SECRET_KEY"] = "test-secret-key-not-for-production"

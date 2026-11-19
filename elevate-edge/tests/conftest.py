"""Test setup for the Elevate Edge app.

The app is a module, not a package, so `elevate-edge/` goes on sys.path. The
secret key, dev switch and database path are set here because the module builds
an app on import; the tests that must see the secret key *missing* clear it again
explicitly.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="elevate-tests-"))
os.environ.setdefault("ELEVATE_DEV", "1")
os.environ.setdefault("ELEVATE_SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("ELEVATE_DB_PATH", str(_TMP / "import-time.db"))

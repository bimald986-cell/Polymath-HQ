#!/usr/bin/env python3
"""Capability scan — compare registry status vs registered study forks.

Produces a President Brief style summary. Does not merge or mutate repos.
Run from repo root or intelligent-agency/:

    python intelligent-agency/scripts/capability_scan.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timezone

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "core" / "capability_registry.yaml"
PROJECTS = ROOT / "core" / "projects.yaml"
ALLOWLIST = ROOT / "core" / "public_api_allowlist.yaml"


def load(path: Path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> int:
    if not REGISTRY.is_file():
        print(f"Missing {REGISTRY}", file=sys.stderr)
        return 1

    reg = load(REGISTRY)
    projects = load(PROJECTS) if PROJECTS.is_file() else {}
    allow = load(ALLOWLIST) if ALLOWLIST.is_file() else {}

    caps = reg.get("capabilities") or {}
    planned = [k for k, v in caps.items() if (v or {}).get("status") in ("planned", "adapter-planned")]
    foundation = [k for k, v in caps.items() if (v or {}).get("status") in ("foundation", "existing-partial")]

    forks = {
        name: meta
        for name, meta in (projects.get("projects") or {}).items()
        if (meta or {}).get("type") in ("study-fork", "skills-library", "reference-catalog")
    }

    allow_count = len((allow.get("endpoints") or []))

    lines = [
        "## President Brief: capability scan",
        "",
        f"**When:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "### Capability status",
        f"- Foundation / partial: {len(foundation)} — {', '.join(sorted(foundation)) or 'none'}",
        f"- Planned: {len(planned)} — {', '.join(sorted(planned)) or 'none'}",
        "",
        "### Registered study / skill / catalog forks",
    ]
    for name, meta in sorted(forks.items()):
        lines.append(f"- **{name}** (`{meta.get('github')}`) — {meta.get('type')} — {(meta.get('notes') or '')[:120]}")

    lines += [
        "",
        f"### Public API allowlist",
        f"- Curated endpoints: {allow_count}",
        f"- File: `core/public_api_allowlist.yaml`",
        "",
        "### Recommended next actions",
        "1. Keep design skills applied on Elevate Edge, HQ dashboard, and AstroLab UI work.",
        "2. Wire PolicyEngine into tool call sites as they are added.",
        "3. Promote allowlist candidates only after ToS/rate-limit review.",
        "",
        "### Decision requested",
        "Review only — this scan does not modify code or merge anything.",
    ]

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

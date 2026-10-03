#!/usr/bin/env python3
"""File a CapabilityRequest into the HQ growth backlog.

Usage (from repo root):
  python intelligent-agency/scripts/growth_intake.py \\
    --by "Research & Development" \\
    --target "Legal" \\
    --name "Patent Scout" \\
    --kind agent \\
    --rationale "Gap in patent landscape routing" \\
    --keywords patent,prior-art,ip-search

Does not modify agency.yaml. Skills / Horizon triage the backlog.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[2]
BACKLOG = ROOT / "core" / "growth" / "capability_requests.yaml"


def next_id(existing: list) -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    n = 1
    used = {r.get("id") for r in existing if isinstance(r, dict)}
    while True:
        cand = f"req-{day}-{n:03d}"
        if cand not in used:
            return cand
        n += 1


def main() -> int:
    p = argparse.ArgumentParser(description="HQ growth intake — file a CapabilityRequest")
    p.add_argument("--by", required=True, help="requested_by (director, R&D, Horizon, human)")
    p.add_argument("--target", required=True, help="target_director or 'new'")
    p.add_argument("--name", required=True, help="proposed agent/skill/director name")
    p.add_argument("--kind", choices=["agent", "skill", "director"], default="agent")
    p.add_argument("--rationale", required=True)
    p.add_argument("--keywords", default="", help="comma-separated")
    p.add_argument("--description", default="")
    p.add_argument("--priority", type=int, default=50)
    p.add_argument("--evidence-type", default="human",
                   choices=["routing_miss", "rnd_finding", "horizon_scan", "human"])
    p.add_argument("--evidence-detail", default="")
    args = p.parse_args()

    BACKLOG.parent.mkdir(parents=True, exist_ok=True)
    if BACKLOG.is_file():
        data = yaml.safe_load(BACKLOG.read_text(encoding="utf-8")) or {}
    else:
        data = {"schema_version": 1, "requests": []}

    requests = data.get("requests") or []
    if not isinstance(requests, list):
        requests = []

    req = {
        "id": next_id(requests),
        "status": "proposed",
        "priority": args.priority,
        "requested_by": args.by,
        "target_director": args.target,
        "proposed_name": args.name,
        "kind": args.kind,
        "rationale": args.rationale.strip(),
        "keywords": [k.strip() for k in args.keywords.split(",") if k.strip()],
        "suggested_description": args.description or "",
        "evidence": [
            {
                "type": args.evidence_type,
                "detail": args.evidence_detail or args.rationale.strip()[:200],
            }
        ],
        "acceptance_criteria": [],
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    requests.append(req)
    data["schema_version"] = data.get("schema_version", 1)
    data["requests"] = requests

    BACKLOG.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    print(f"Filed {req['id']} → {BACKLOG.relative_to(ROOT)}")
    print(f"  {req['kind']}: {req['proposed_name']} under {req['target_director']}")
    print("Skills / Horizon will triage. No org-chart change until President merges.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

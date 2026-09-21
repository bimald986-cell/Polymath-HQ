#!/usr/bin/env python3
"""Command-line entry point for the Intelligent Agency.

Examples:
    python cli.py tree
    python cli.py list
    python cli.py find "how do I fertilise my tomato crop"
    python cli.py ask  "how do I fertilise my tomato crop"
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from agency import build_agency  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Intelligent Agency CLI")
    parser.add_argument("--config", default=None, help="Path to agency.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("tree", help="Print the org chart")
    sub.add_parser("list", help="List all directors")

    p_find = sub.add_parser("find", help="Show which fields match a query")
    p_find.add_argument("query", nargs="+")

    p_ask = sub.add_parser("ask", help="Route a request and get an answer")
    p_ask.add_argument("query", nargs="+")

    args = parser.parse_args(argv)
    president = build_agency(args.config) if args.config else build_agency()

    if args.command == "tree":
        print(president.tree())
        return 0

    if args.command == "list":
        for d in president.directors:
            print(f"- {d.name}: {d.description} ({len(d.agents)} agents)")
        return 0

    query = " ".join(args.query)

    if args.command == "find":
        print(f"Fields most related to: {query!r}\n")
        for director, sc in president.find_directors(query, top_k=5):
            print(f"  {sc:5.2f}  {director.name} -- {director.description}")
        return 0

    if args.command == "ask":
        result = president.handle(query)
        print(f"President: {result['president']}")
        print(f"Director : {result['director']}")
        print(f"Agent    : {result['agent']}")
        print("-" * 50)
        print(result["answer"])
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

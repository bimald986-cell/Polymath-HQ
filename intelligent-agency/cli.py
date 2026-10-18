#!/usr/bin/env python3
"""Command-line entry point for Polymath HQ Intelligent Agency."""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from agency import build_agency  # noqa: E402
from agency.builtin_tools import default_registry  # noqa: E402
from agency.policy import default_engine  # noqa: E402
from agency.tool_agent import run_tool_loop  # noqa: E402
from agency.tools import ToolDispatcher  # noqa: E402


def _parse_args(raw_args):
    """``--arg key=value`` where the value is JSON when it parses, else a string."""
    arguments = {}
    for item in raw_args:
        if "=" not in item:
            raise SystemExit(f"--arg expects KEY=VALUE, got {item!r}")
        key, value = item.split("=", 1)
        try:
            arguments[key] = json.loads(value)
        except json.JSONDecodeError:
            arguments[key] = value
    return arguments


def _run_tool_command(args) -> int:
    """The tool-use channel: list tools, invoke one, or run the loop for real."""
    registry = default_registry(args.repo_root)
    if args.command == "tools":
        print(json.dumps(registry.specs(), indent=2, sort_keys=True))
        return 0
    dispatcher = ToolDispatcher(registry, default_engine(), actor=args.actor)
    if args.command == "tool":
        result = dispatcher.dispatch(args.name, _parse_args(args.arg), actor=args.actor)
        print(json.dumps(result.as_dict(), indent=2, default=str))
        return 0 if result.ok else 1
    plan = None
    if args.plan:
        with open(args.plan, "r", encoding="utf-8") as handle:
            plan = json.load(handle)
    result = run_tool_loop(
        task=args.query,
        registry=registry,
        policy=dispatcher.policy,
        plan=plan,
        max_steps=args.max_steps,
        actor=args.actor,
        out_path=args.out,
    )
    print(json.dumps(result.as_dict(), indent=2, default=str))
    return 0 if result.status == "completed" else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Polymath HQ Intelligent Agency CLI")
    parser.add_argument("--config", default=None, help="Path to agency.yaml")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("tree", help="Print the org chart")
    sub.add_parser("list", help="List all directors")
    sub.add_parser("advisor-permissions", help="Show Horizon's repository authority")

    p_find = sub.add_parser("find", help="Show which fields match a query")
    p_find.add_argument("query", nargs="+")
    p_ask = sub.add_parser("ask", help="Route a request and get an answer")
    p_ask.add_argument("query", nargs="+")
    p_advise = sub.add_parser("advise", help="Ask Horizon for an improvement/research brief")
    p_advise.add_argument("topic", nargs="+")

    p_tools = sub.add_parser("tools", help="List the tools an agent can actually call")
    p_tools.add_argument("--repo-root", default=None, help="The single root tools may work in")

    p_tool = sub.add_parser("tool", help="Invoke one tool through the policy gate")
    p_tool.add_argument("name")
    p_tool.add_argument("--arg", action="append", default=[], metavar="KEY=VALUE")
    p_tool.add_argument("--repo-root", default=None)
    p_tool.add_argument("--actor", default="cli")

    p_loop = sub.add_parser("loop", help="Run the bounded agent loop with real tools")
    p_loop.add_argument("--query", default="", help="The task the loop works on")
    p_loop.add_argument(
        "--plan",
        default=None,
        help="JSON file holding a list of {tool, arguments} calls to execute in order",
    )
    p_loop.add_argument("--max-steps", type=int, default=6)
    p_loop.add_argument("--repo-root", default=None)
    p_loop.add_argument("--out", default=None, help="Append the run result as one JSON line here")
    p_loop.add_argument("--actor", default="cli")

    args = parser.parse_args(argv)

    if args.command in ("tools", "tool", "loop"):
        return _run_tool_command(args)

    president = build_agency(args.config) if args.config else build_agency()

    if args.command == "tree":
        print(president.tree())
        return 0
    if args.command == "list":
        for d in president.directors:
            print(f"- {d.name}: {d.description} ({len(d.agents)} agents)")
        return 0
    if args.command == "advisor-permissions":
        for action, allowed in president.advisor.permissions().items():
            print(f"{'YES' if allowed else 'NO ':3}  {action}")
        return 0
    if args.command == "advise":
        print(president.ask_advisor(" ".join(args.topic)))
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

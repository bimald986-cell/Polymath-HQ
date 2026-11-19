#!/usr/bin/env python3
"""Operator CLI for Elevate Edge entitlements. No web surface, no payment provider.

    python admin.py grant  someone@example.com pro     # give Pro (200 AI drafts / 30 days)
    python admin.py grant  someone@example.com free    # back to the free tier
    python admin.py revoke someone@example.com         # same as `grant ... free`
    python admin.py show   someone@example.com         # plan and usage

The plan flag is the only entitlement. Nothing here takes money: this is the
operator's switch until a checkout webhook exists, and the webhook will call the
same `store.grant_plan(email, plan)` seam. The database is the app's own
(`ELEVATE_DB_PATH`, default `elevate-edge/data/elevate.db`).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import store

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "elevate.db"


def _open_db() -> "store.sqlite3.Connection":
    path = os.getenv("ELEVATE_DB_PATH") or str(DEFAULT_DB_PATH)
    store.init_db(path)
    return store.connect(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="admin.py", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    grant = sub.add_parser("grant", help="set a user's plan")
    grant.add_argument("email")
    grant.add_argument("plan", nargs="?", default="pro", choices=sorted(store.PLANS))

    revoke = sub.add_parser("revoke", help="put a user back on the free plan")
    revoke.add_argument("email")

    show = sub.add_parser("show", help="print a user's plan and AI usage")
    show.add_argument("email")

    args = parser.parse_args(argv)
    conn = _open_db()
    try:
        if args.command == "show":
            user = store.get_user_by_email(conn, args.email)
            if user is None:
                print(f"no such user: {store.normalize_email(args.email)}", file=sys.stderr)
                return 1
            usage = store.ai_usage(conn, user["id"])
            print(
                f"{user['email']}: plan={usage['plan']} "
                f"used={usage['used']}/{usage['limit']} "
                f"remaining={usage['remaining']} since {usage['period_start']}"
            )
            return 0

        plan = "free" if args.command == "revoke" else args.plan
        if not store.grant_plan(conn, args.email, plan):
            print(f"no such user: {store.normalize_email(args.email)}", file=sys.stderr)
            return 1
        print(f"{store.normalize_email(args.email)} is now on the {plan} plan "
              f"({store.PLANS[plan]} AI drafts per 30 days)")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

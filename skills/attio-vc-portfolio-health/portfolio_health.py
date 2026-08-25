#!/usr/bin/env python3
"""
attio-vc-portfolio-health: post-investment tracking hygiene for a VC/PE
fund's own CRM -- board-meeting cadence and KPI-reporting cadence across the
portfolio (companies already invested in), derived from linked Notes'
title/content. Supports both Attio and Affinity as the source CRM.

Usage:
    ATTIO_API_KEY=<token> python portfolio_health.py
    AFFINITY_API_KEY=<key> python portfolio_health.py --source affinity
    python portfolio_health.py --source attio --object investments
    python portfolio_health.py --source affinity --list "Portfolio"
    python portfolio_health.py --board-days 60 --kpi-days 45
    python portfolio_health.py --json
    python portfolio_health.py --source affinity --full --yes-i-know

Output: markdown report to stdout (or JSON with --json). Exit code 0 on
success, 2 on a usage/detection error.

Strictly read-only on both platforms: GET and POST-query calls only (Attio),
GET calls only (Affinity). No PATCH, PUT, or POST-write calls anywhere.

See _common.py for the source-agnostic cadence scoring and rendering,
_attio.py and _affinity.py for the two backends. Each backend module is
self-contained (does not import from the sibling skill folders), matching
this repo's default convention that every skill stays independently
copy-able -- see attio-vc-ic-memo-prep/SKILL.md for why.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import requests

import _affinity as affinity
import _attio as attio
import _common as common


def resolve_source(args, attio_token: str | None, affinity_token: str | None) -> str:
    if args.source:
        return args.source
    have_attio = bool(attio_token)
    have_affinity = bool(affinity_token)
    if have_attio and not have_affinity:
        return "attio"
    if have_affinity and not have_attio:
        return "affinity"
    if have_attio and have_affinity:
        print(
            "error: both ATTIO_API_KEY and AFFINITY_API_KEY (or their --token flags) are set. "
            "Pass --source attio or --source affinity explicitly.",
            file=sys.stderr,
        )
    else:
        print(
            "error: no token found. Set ATTIO_API_KEY or AFFINITY_API_KEY (or pass --token / "
            "--affinity-token), and pass --source explicitly.",
            file=sys.stderr,
        )
    sys.exit(2)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Post-investment cadence hygiene (board meetings, KPI reporting) for a VC/PE "
        "fund's portfolio, from Attio or Affinity."
    )
    p.add_argument("--source", choices=["attio", "affinity"], help="Which CRM to read from. Auto-detected if only one token is set.")
    p.add_argument("--token", help="Attio API token (default: $ATTIO_API_KEY or $ATTIO_OAUTH2)")
    p.add_argument("--affinity-token", help="Affinity API key (default: $AFFINITY_API_KEY)")
    p.add_argument("--object", help="[Attio] Explicit object slug. Overrides auto-detection.")
    p.add_argument("--list", dest="list_arg", help="[Affinity] Explicit list id or exact name. Overrides auto-detection.")
    p.add_argument("--board-days", type=int, default=common.DEFAULT_BOARD_DAYS, help=f"Days before a board-meeting note is stale (default: {common.DEFAULT_BOARD_DAYS})")
    p.add_argument("--kpi-days", type=int, default=common.DEFAULT_KPI_DAYS, help=f"Days before a KPI-update note is stale (default: {common.DEFAULT_KPI_DAYS})")
    p.add_argument("--sample-size", type=int, help="[Affinity] Override the default entry sample size (default: 75).")
    p.add_argument("--json", action="store_true", help="Output JSON instead of markdown")
    p.add_argument("--full", action="store_true", help="Paginate every record/entry and every note instead of sampling.")
    p.add_argument("--yes-i-know", action="store_true", help="[Affinity] Confirm you understand --full on the stage-filtered fallback path costs one /field-values call per entry.")
    args = p.parse_args()

    attio_token = args.token or os.environ.get("ATTIO_API_KEY") or os.environ.get("ATTIO_OAUTH2")
    affinity_token = args.affinity_token or os.environ.get("AFFINITY_API_KEY")
    source = resolve_source(args, attio_token, affinity_token)

    if source == "attio":
        if not attio_token:
            print("error: --source attio requires --token or ATTIO_API_KEY", file=sys.stderr)
            return 2
        return run_attio(attio_token, args)
    else:
        if not affinity_token:
            print("error: --source affinity requires --affinity-token or AFFINITY_API_KEY", file=sys.stderr)
            return 2
        return run_affinity(affinity_token, args)


def run_attio(token: str, args) -> int:
    try:
        ws = attio.fetch_self(token)
    except requests.HTTPError as e:
        print(f"error: auth failed (HTTP {e.response.status_code}). Token invalid or revoked.", file=sys.stderr)
        return 2

    try:
        result = attio.load(token, args.object, args.full)
    except attio.DetectionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except requests.HTTPError as e:
        status = getattr(e.response, "status_code", "?")
        print(f"error: Attio API call failed (HTTP {status}).", file=sys.stderr)
        return 2

    meta = {
        "fund_name": ws.get("workspace_name", "Unknown"),
        "workspace_slug": ws.get("workspace_slug", ""),
        "source_label": "Attio",
        "run_ts": _now_str(),
        "detection_note": result.detection_note,
        "scope_note": result.scope_note,
        "board_days": args.board_days,
        "kpi_days": args.kpi_days,
    }
    return _render_and_print(meta, result.companies, args)


def run_affinity(key: str, args) -> int:
    try:
        result = affinity.load(key, args.list_arg, args.full, args.sample_size, args.yes_i_know)
    except affinity.DetectionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except affinity.BudgetGateError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except requests.HTTPError as e:
        status = getattr(e.response, "status_code", "?")
        print(f"error: Affinity API call failed (HTTP {status}). Check the key and its permissions.", file=sys.stderr)
        return 2

    meta = {
        "fund_name": "Affinity workspace",
        "workspace_slug": "affinity",
        "source_label": "Affinity",
        "run_ts": _now_str(),
        "detection_note": result.detection_note,
        "scope_note": result.scope_note,
        "board_days": args.board_days,
        "kpi_days": args.kpi_days,
    }
    return _render_and_print(meta, result.companies, args)


def _render_and_print(meta: dict, companies, args) -> int:
    rows = common.build_rows(companies, args.board_days, args.kpi_days)
    board = common.score_dimension(rows, "board", args.board_days, 50, "Board-meeting cadence")
    kpi = common.score_dimension(rows, "kpi", args.kpi_days, 50, "KPI-reporting cadence")

    if args.json:
        print(json.dumps(common.render_json(meta, rows, board, kpi), indent=2))
    else:
        print(common.render_markdown(meta, rows, board, kpi))
    return 0


def _now_str() -> str:
    import datetime

    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
attio-vc-coinvestor-map: relationship-density check on co-investor/syndicate
tracking across a VC/PE fund's own deal pipeline AND portfolio. Supports
both Attio and Affinity as the source CRM.

Usage:
    ATTIO_API_KEY=<token> python coinvestor_map.py
    AFFINITY_API_KEY=<key> python coinvestor_map.py --source affinity
    python coinvestor_map.py --source attio --object investments
    python coinvestor_map.py --source affinity --list "Deals"
    python coinvestor_map.py --json
    python coinvestor_map.py --source affinity --full --yes-i-know

Output: markdown report to stdout (or JSON with --json). Exit code 0 on
success, 2 on a usage/detection error.

Strictly read-only on both platforms: GET and POST-query calls only (Attio),
GET calls only (Affinity). No PATCH, PUT, or POST-write calls anywhere.

Scope boundary: this tool reports coverage and a ranked frequency table from
an explicit, human-entered co-investor/syndicate field only. It does not
attempt Affinity's own relationship-strength/interaction-scoring product
(their actual moat, built on private email/calendar sync data no public API
exposes) -- see SKILL.md.

See _common.py for the source-agnostic report model and rendering,
_attio.py and _affinity.py for the two backends. Each backend module is
self-contained (does not import from the sibling skill folders), matching
this repo's default convention that every skill stays independently
copy-able.
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
        description="Co-investor / syndicate tracking coverage + ranked frequency map for a VC/PE "
        "fund's deals, from Attio or Affinity."
    )
    p.add_argument("--source", choices=["attio", "affinity"], help="Which CRM to read from. Auto-detected if only one token is set.")
    p.add_argument("--token", help="Attio API token (default: $ATTIO_API_KEY or $ATTIO_OAUTH2)")
    p.add_argument("--affinity-token", help="Affinity API key (default: $AFFINITY_API_KEY)")
    p.add_argument("--object", help="[Attio] Explicit object slug. Overrides auto-detection.")
    p.add_argument("--list", dest="list_arg", help="[Affinity] Explicit list id or exact name. Overrides auto-detection (normally unions pipeline + portfolio lists).")
    p.add_argument("--sample-size", type=int, help="[Affinity] Override the default entity sample size (default: 75).")
    p.add_argument("--json", action="store_true", help="Output JSON instead of markdown")
    p.add_argument("--full", action="store_true", help="[Attio] paginate every record. [Affinity] check every entity's co-investor field -- real per-entity spend, requires --yes-i-know.")
    p.add_argument("--yes-i-know", action="store_true", help="[Affinity] Confirm you understand --full calls /field-values once per entity (no bulk endpoint exists).")
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
        "field_note": result.field_note,
    }
    return _render_and_print(meta, result, args)


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
        "fund_name": "Affinity account",
        "workspace_slug": "affinity",
        "source_label": "Affinity",
        "run_ts": _now_str(),
        "detection_note": result.detection_note,
        "scope_note": result.scope_note,
        "field_note": result.field_note,
    }
    return _render_and_print(meta, result, args)


def _render_and_print(meta: dict, result, args) -> int:
    if result.field_note is None:
        if args.json:
            print(json.dumps(common.render_json(meta, None), indent=2))
        else:
            print(common.render_not_tracked(meta))
        return 0

    report = common.build_report(result.deals)
    if args.json:
        print(json.dumps(common.render_json(meta, report), indent=2))
    else:
        print(common.render_markdown(meta, report))
    return 0


def _now_str() -> str:
    import datetime

    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


if __name__ == "__main__":
    sys.exit(main())

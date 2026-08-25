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
import _vc_config as vc_config


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
    p.add_argument("--object", help="[Attio] Explicit object slug. Overrides auto-detection and any cached config.")
    p.add_argument("--list", dest="list_arg", help="[Affinity] Explicit list id or exact name. Overrides auto-detection and any cached config.")
    p.add_argument(
        "--config",
        help="Path to a saved workspace config (default: .vc-skills-config/<workspace-slug>.json). "
        "See README's 'First run' section and this skill's SKILL.md.",
    )
    p.add_argument(
        "--detect-only",
        action="store_true",
        help="Auto-detect the portfolio object/list and its candidate invested-status titles only, "
        "print as JSON, and exit -- no record/note/field-value calls made, no cadence scored. Used "
        "for first-run setup; see README.",
    )
    p.add_argument(
        "--board-days",
        type=int,
        default=None,
        help=f"Days before a board-meeting note is stale (default: {common.DEFAULT_BOARD_DAYS}, or a cached config's board_days if set)",
    )
    p.add_argument(
        "--kpi-days",
        type=int,
        default=None,
        help=f"Days before a KPI-update note is stale (default: {common.DEFAULT_KPI_DAYS}, or a cached config's kpi_days if set)",
    )
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

    workspace_slug = ws.get("workspace_slug", "")

    if args.detect_only:
        return _detect_only_attio(token, workspace_slug)

    config = vc_config.load_config(workspace_slug, args.config)
    object_arg = args.object or (config.get("object") if config else None)
    invested_override = (
        set(config["invested_status_titles"])
        if config and config.get("invested_status_titles")
        else None
    )

    try:
        result = attio.load(token, object_arg, args.full, invested_override)
    except attio.DetectionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except requests.HTTPError as e:
        status = getattr(e.response, "status_code", "?")
        print(f"error: Attio API call failed (HTTP {status}).", file=sys.stderr)
        return 2

    board_days = args.board_days if args.board_days is not None else (config or {}).get("board_days", common.DEFAULT_BOARD_DAYS)
    kpi_days = args.kpi_days if args.kpi_days is not None else (config or {}).get("kpi_days", common.DEFAULT_KPI_DAYS)

    meta = {
        "fund_name": ws.get("workspace_name", "Unknown"),
        "workspace_slug": workspace_slug,
        "source_label": "Attio",
        "run_ts": _now_str(),
        "detection_note": result.detection_note,
        "scope_note": result.scope_note,
        "board_days": board_days,
        "kpi_days": kpi_days,
    }
    return _render_and_print(meta, result.companies, board_days, kpi_days, args)


def run_affinity(key: str, args) -> int:
    if args.detect_only:
        return _detect_only_affinity(key)

    # Affinity has no self/whoami-equivalent identity call in this repo (see
    # module docstrings) -- "affinity" is the same static workspace_slug the
    # rest of this script already uses in `meta` below, so it's also what a
    # cached config is looked up (and saved) under. One config file per
    # machine/checkout covers every Affinity account run from it; a fund
    # juggling multiple Affinity accounts from the same directory should pass
    # --config explicitly per account.
    workspace_slug = "affinity"
    config = vc_config.load_config(workspace_slug, args.config)
    list_arg = args.list_arg or (config.get("list") if config else None)
    invested_override = (
        set(config["invested_status_titles"])
        if config and config.get("invested_status_titles")
        else None
    )

    try:
        result = affinity.load(key, list_arg, args.full, args.sample_size, args.yes_i_know, invested_override)
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

    board_days = args.board_days if args.board_days is not None else (config or {}).get("board_days", common.DEFAULT_BOARD_DAYS)
    kpi_days = args.kpi_days if args.kpi_days is not None else (config or {}).get("kpi_days", common.DEFAULT_KPI_DAYS)

    meta = {
        "fund_name": "Affinity workspace",
        "workspace_slug": workspace_slug,
        "source_label": "Affinity",
        "run_ts": _now_str(),
        "detection_note": result.detection_note,
        "scope_note": result.scope_note,
        "board_days": board_days,
        "kpi_days": kpi_days,
    }
    return _render_and_print(meta, result.companies, board_days, kpi_days, args)


def _detect_only_attio(token: str, workspace_slug: str) -> int:
    """Enough calls to show a human what --config would otherwise guess:
    the portfolio object (or deal-object fallback) and, on the fallback
    path only, the candidate invested-status titles. No /records, /notes,
    or scoring -- matches the "cheap, fast, side-effect-free" contract in
    the README's First run section.
    """
    objects = attio.fetch_objects(token)
    deal_obj, deal_candidates = attio.detect_deal_object(objects)
    portfolio_obj = attio.detect_portfolio_object(objects, deal_obj.get("api_slug") if deal_obj else None)

    out: dict = {
        "source": "attio",
        "workspace_slug": workspace_slug,
        "object": None,
        "uses_status_filter": False,
        "status_titles_all": [],
        "invested_status_titles_guess": [],
        "deal_object_candidates": deal_candidates,
        "board_days_default": common.DEFAULT_BOARD_DAYS,
        "kpi_days_default": common.DEFAULT_KPI_DAYS,
    }

    if portfolio_obj is not None:
        out["object"] = portfolio_obj.get("api_slug")
        out["note"] = (
            "Distinct portfolio object found -- every record in it counts as a portfolio company, "
            "no status filtering needed. Confirm `object`, `board_days`, `kpi_days` with the human, "
            f"then save to .vc-skills-config/{workspace_slug}.json."
        )
    elif deal_obj is not None:
        out["object"] = deal_obj.get("api_slug")
        out["uses_status_filter"] = True
        attrs = attio.fetch_attributes(token, deal_obj.get("api_slug"))
        stage_attr = attio.find_stage_attribute(attrs)
        if stage_attr is not None:
            statuses = attio.fetch_statuses(token, deal_obj.get("api_slug"), stage_attr.get("api_slug"))
            out["status_titles_all"] = [s.get("title") for s in statuses if s.get("title")]
            out["invested_status_titles_guess"] = sorted(attio.classify_invested_statuses(statuses))
        out["note"] = (
            "No distinct portfolio object found; falling back to this deal object filtered by "
            "status. Confirm `object`, `invested_status_titles_guess` (does this list match your "
            f"closed-won statuses?), `board_days`, `kpi_days` with the human, then save to "
            f".vc-skills-config/{workspace_slug}.json."
        )
    else:
        out["note"] = (
            "Could not confidently identify a portfolio or deal/investment object in this "
            "workspace's schema. Re-run with --object <slug>."
        )

    print(json.dumps(out, indent=2))
    return 0


def _detect_only_affinity(key: str) -> int:
    """Affinity equivalent of _detect_only_attio -- lists and field metadata
    only, never a per-entity /field-values call (that's the expensive part
    this whole config system exists to make a human confirm once instead of
    the tool re-guessing, or worse, re-spending, on every run).
    """
    lists = affinity.fetch_lists(key)
    portfolio_list = affinity.detect_portfolio_list(lists)

    out: dict = {
        "source": "affinity",
        "workspace_slug": "affinity",
        "list": None,
        "uses_status_filter": False,
        "status_field": None,
        "status_titles_all": [],
        "invested_status_titles_guess": [],
        "board_days_default": common.DEFAULT_BOARD_DAYS,
        "kpi_days_default": common.DEFAULT_KPI_DAYS,
    }

    if portfolio_list is not None:
        out["list"] = portfolio_list.get("name")
        out["note"] = (
            "Distinct portfolio list found -- every entry in it counts as a portfolio company, no "
            "status filtering needed. Confirm `list`, `board_days`, `kpi_days` with the human, then "
            "save to .vc-skills-config/affinity.json."
        )
    else:
        deal_list, candidates = affinity.detect_deal_list(lists)
        out["deal_list_candidates"] = candidates
        if deal_list is not None:
            out["list"] = deal_list.get("name")
            out["uses_status_filter"] = True
            fields = affinity.fetch_fields(key, list_id=deal_list["id"])
            status_field = next(
                (f for f in fields if any(affinity._matches_keyword((f.get("name") or "").lower(), kw) for kw in affinity.STATUS_FIELD_KEYWORDS)),
                None,
            )
            if status_field is not None:
                out["status_field"] = status_field.get("name")
                texts, guess = [], set()
                for opt in status_field.get("dropdown_options") or []:
                    title = opt.get("text") or ""
                    texts.append(title)
                    low = title.lower()
                    if any(kw in low for kw in affinity.LOST_KEYWORDS):
                        continue
                    if any(kw in low for kw in affinity.INVESTED_KEYWORDS):
                        guess.add(title)
                out["status_titles_all"] = texts
                out["invested_status_titles_guess"] = sorted(guess)
            out["note"] = (
                "No distinct portfolio list found; falling back to this deal list filtered by "
                "status. Confirm `list`, `invested_status_titles_guess` (does this list match your "
                "closed-won statuses?), `board_days`, `kpi_days` with the human, then save to "
                ".vc-skills-config/affinity.json."
            )
        else:
            out["note"] = (
                "Could not confidently identify a portfolio or deal/investment list in this "
                "Affinity account. Re-run with --list <id-or-name>."
            )

    print(json.dumps(out, indent=2))
    return 0


def _render_and_print(meta: dict, companies, board_days: int, kpi_days: int, args) -> int:
    rows = common.build_rows(companies, board_days, kpi_days)
    board = common.score_dimension(rows, "board", board_days, 50, "Board-meeting cadence")
    kpi = common.score_dimension(rows, "kpi", kpi_days, 50, "KPI-reporting cadence")

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

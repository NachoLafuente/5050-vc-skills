#!/usr/bin/env python3
"""
attio-vc-ic-memo-prep: pull the raw materials for one deal's IC memo skeleton
out of a VC/PE fund's own Attio workspace -- structured Deal Header fields
(round size, valuation, security type, ownership target, sector, stage,
source of intro) plus every linked Note's full chronological text, for one
named or ID'd deal.

Usage:
    ATTIO_API_KEY=<token> python ic_memo_prep.py --deal "Acme Robotics"
    python ic_memo_prep.py --token <token> --deal <record-id>
    python ic_memo_prep.py --deal "Acme Robotics" --object investments
    python ic_memo_prep.py --deal "Acme Robotics" --json

Output: markdown to stdout (or JSON with --json). Exit code 0 on success,
2 on a usage/lookup error (bad token, ambiguous or missing deal, etc.).

This script does mechanical retrieval only -- it does NOT classify note
content into Market / Team / Product / Risks sections, does NOT draft an
investment thesis, and does NOT invent anything not already in the workspace.
That classification is language judgment, not data retrieval, and is the job
of whoever (Claude, running this skill per its SKILL.md) reads the raw notes
this script prints. See SKILL.md for the instructions that govern that step.

This is a standalone, self-contained script -- deliberately not sharing code
with the sibling skill attio-vc-ic-pipeline-prep (which does share an
internal module between its own two halves, see that skill's _common.py for
why). Each skill in this repo stays independently copy-able on its own,
matching this repo's default convention; the pipeline-prep merge is the one
documented exception, for two logics living in one skill.

Strictly read-only: GET and POST-query calls only. No PATCH, PUT, or
POST-write calls appear anywhere in this file.

Auto-detects the deal/investment/opportunity object by api_slug/noun
matching, identical in approach to the sibling skill; override with
--object <slug> if detection is ambiguous or picks the wrong object.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

API_BASE = "https://api.attio.com/v2"
SAMPLE_LIMIT = 500
ATTIO_PAGE_MAX = 500
HTTP_TIMEOUT = 30

# Attio's /notes endpoint caps `limit` at 50 (records/lists allow up to 500).
# Confirmed against the public OpenAPI spec (api.attio.com/openapi/api) --
# mixing this up silently truncates every notes page.
NOTES_PAGE_LIMIT = 50

# Object-detection keywords: matched as loose substrings against
# api_slug/singular_noun/plural_noun. Identical approach to the sibling
# skill's deal-object detection -- workspaces commonly pluralize or compound
# these ("deal", "deals", "portfolio_company", "portfolio_companies").
DEAL_OBJECT_KEYWORDS = ["deal", "investment", "opportunit", "portfolio compan", "pipeline"]

# Deal Header field specs: (display label, keywords matched against
# attribute title/api_slug). Whole-word matching (see _matches_keyword) --
# keywords are kept deliberately narrow per field so "Sector" doesn't also
# swallow an unrelated "Category" field meant for something else on a given
# workspace. A workspace that names things very differently from these
# conventions will show that field as "not tracked" -- a real gap this tool
# surfaces, not a bug, but worth knowing as a failure mode (see SKILL.md).
HEADER_FIELD_SPECS: list[tuple[str, list[str]]] = [
    (
        "Round size / raise amount",
        ["round size", "raise amount", "raise size", "amount raised", "round amount", "check size", "raise"],
    ),
    (
        "Valuation",
        ["valuation", "pre money valuation", "post money valuation", "pre money", "post money", "cap"],
    ),
    (
        "Security type / instrument",
        ["security type", "instrument", "security", "note type", "safe", "convertible note"],
    ),
    (
        "Ownership / stake percentage",
        ["ownership", "stake", "equity percentage", "ownership target", "fully diluted"],
    ),
    (
        "Sector",
        ["sector", "vertical", "industry", "focus area", "sub sector", "market segment"],
    ),
    (
        "Stage",
        ["stage", "pipeline stage", "deal stage", "company stage", "round stage"],
    ),
    (
        "Source of intro",
        ["source of intro", "how sourced", "referred by", "referral", "sourced by", "intro source", "lead source", "source"],
    ),
]

# Candidate keys Attio might use for a note's full text content -- the shape
# isn't nailed down the same way as record values, so this checks several
# plausible keys rather than assuming one. See extract_note_text().
NOTE_CONTENT_KEYS = ("content_plaintext", "content_markdown", "content", "plaintext", "markdown", "text", "body")

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


def call(token: str, method: str, path: str, body: dict | None = None) -> Any:
    url = f"{API_BASE}{path}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.request(method, url, headers=headers, json=body, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# --- API helpers ----------------------------------------------------------------


def fetch_self(token: str) -> dict:
    return call(token, "GET", "/self")


def fetch_objects(token: str) -> list[dict]:
    return call(token, "GET", "/objects").get("data", [])


def fetch_attributes(token: str, object_slug: str) -> list[dict]:
    return call(token, "GET", f"/objects/{object_slug}/attributes").get("data", [])


def fetch_records(token: str, object_slug: str, full: bool = False, limit: int = SAMPLE_LIMIT) -> list[dict]:
    if not full:
        body = {"limit": limit, "offset": 0}
        return call(token, "POST", f"/objects/{object_slug}/records/query", body).get("data", [])

    all_records: list[dict] = []
    offset = 0
    while True:
        body = {"limit": ATTIO_PAGE_MAX, "offset": offset}
        page = call(token, "POST", f"/objects/{object_slug}/records/query", body).get("data", [])
        if not page:
            break
        all_records.extend(page)
        if len(page) < ATTIO_PAGE_MAX:
            break
        offset += ATTIO_PAGE_MAX
    return all_records


def fetch_record_by_id(token: str, object_slug: str, record_id: str) -> dict | None:
    """Direct single-record lookup. Returns None on 404 (not this object /
    wrong id), re-raises any other HTTP error (e.g. auth failure) so it
    surfaces clearly instead of being read as "not found".
    """
    try:
        return call(token, "GET", f"/objects/{object_slug}/records/{record_id}").get("data")
    except requests.HTTPError as e:
        if getattr(e.response, "status_code", None) == 404:
            return None
        raise


def fetch_record_notes(token: str, object_slug: str, record_id: str) -> list[dict]:
    """Every Note linked to one record, oldest first.

    Same paginated GET /v2/notes?parent_object=... scan the sibling skill
    uses for a whole-object sweep, but scoped with parent_record_id to just
    this one record -- so it always paginates in full rather than sampling;
    one deal's note volume is small enough that this is cheap.
    """
    notes: list[dict] = []
    offset = 0
    while True:
        path = (
            f"/notes?parent_object={object_slug}&parent_record_id={record_id}"
            f"&limit={NOTES_PAGE_LIMIT}&offset={offset}"
        )
        page = call(token, "GET", path).get("data", [])
        notes.extend(page)
        if len(page) < NOTES_PAGE_LIMIT:
            break
        offset += NOTES_PAGE_LIMIT
    notes.sort(key=lambda n: n.get("created_at") or "")
    return notes


def extract_note_text(note: dict) -> str | None:
    for key in NOTE_CONTENT_KEYS:
        val = note.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return None


def fetch_note_body(token: str, note_id: str) -> str | None:
    """Fallback single-note GET, used only if the list response didn't already
    carry full text under one of NOTE_CONTENT_KEYS. Fine to do per-note here
    (unlike a whole-object scan) since this tool only ever looks at one
    deal's notes at a time.
    """
    try:
        data = call(token, "GET", f"/notes/{note_id}").get("data") or {}
    except requests.HTTPError:
        return None
    return extract_note_text(data)


def full_note_text(token: str, note: dict) -> str:
    text = extract_note_text(note)
    if text:
        return text
    note_id = (note.get("id") or {}).get("note_id")
    if isinstance(note_id, str):
        fetched = fetch_note_body(token, note_id)
        if fetched:
            return fetched
    return "(note text unavailable -- could not read a content field on the note or its body)"


# --- Deal-object detection (same approach as the sibling skill) -----------------


def detect_deal_object(objects: list[dict]) -> tuple[dict | None, list[str]]:
    candidates: list[tuple[int, dict]] = []
    for obj in objects:
        slug = (obj.get("api_slug") or "").lower()
        singular = (obj.get("singular_noun") or "").lower()
        plural = (obj.get("plural_noun") or "").lower()
        haystack = f"{slug} {singular} {plural}".replace("_", " ")
        if slug == "deals":
            candidates.append((100, obj))
            continue
        score = sum(10 for kw in DEAL_OBJECT_KEYWORDS if kw in haystack)
        if score:
            candidates.append((score, obj))

    candidates.sort(key=lambda c: -c[0])
    slugs = [c[1].get("api_slug", "?") for c in candidates]
    if not candidates:
        return None, []
    if len(candidates) == 1 or candidates[0][0] > candidates[1][0]:
        return candidates[0][1], slugs
    return None, slugs


def _matches_keyword(haystack: str, keyword: str) -> bool:
    return re.search(r"\b" + re.escape(keyword) + r"s?\b", haystack) is not None


def find_attributes(attrs: list[dict], keywords: list[str]) -> list[dict]:
    matches = []
    for attr in attrs:
        slug = (attr.get("api_slug") or "").lower()
        title = (attr.get("title") or "").lower()
        haystack = f"{slug} {title}".replace("_", " ").replace("-", " ")
        if any(_matches_keyword(haystack, kw) for kw in keywords):
            matches.append(attr)
    return matches


def record_name(record: dict) -> str:
    """Best-effort display name for a record (same shape-tolerant logic as
    the sibling skill's record_name -- text/personal-name/domain/email all
    stash the display string under a different key).
    """
    values = (record.get("values") or {}).get("name") or []
    if isinstance(values, list) and values:
        entry = values[0]
        if isinstance(entry, dict):
            for key in ("value", "full_name", "domain", "email_address"):
                if entry.get(key):
                    return str(entry[key])
    rid = (record.get("id") or {}).get("record_id") or "?"
    return f"(unnamed {rid[:8]})"


# --- Value formatting -------------------------------------------------------------


def current_entries(entries: list) -> list[dict]:
    """The currently-active entries in a historicized Attio value array
    (active_until is None -- same "what's true right now" marker the sibling
    skill uses for status-type attributes, generalized here to any attribute
    type, since every Attio attribute value is historicized the same way).
    Falls back to the raw list if nothing carries that marker.
    """
    dicts = [e for e in entries if isinstance(e, dict)]
    current = [e for e in dicts if e.get("active_until") is None]
    return current if current else dicts


def _format_single_value(entry: dict) -> str | None:
    if entry.get("currency_value") is not None:
        code = entry.get("currency_code") or ""
        return f"{entry['currency_value']} {code}".strip()
    if entry.get("value") is not None:
        return str(entry["value"])
    status = entry.get("status")
    if isinstance(status, dict) and status.get("title"):
        return status["title"]
    option = entry.get("option")
    if isinstance(option, dict) and option.get("title"):
        return option["title"]
    if entry.get("full_name"):
        return str(entry["full_name"])
    if entry.get("domain"):
        return str(entry["domain"])
    if entry.get("email_address"):
        return str(entry["email_address"])
    target_id = entry.get("target_record_id")
    if target_id:
        return f"(linked record {str(target_id)[:8]})"
    return None


def format_active_values(entries: list) -> str | None:
    parts = [p for p in (_format_single_value(e) for e in current_entries(entries)) if p]
    return "; ".join(parts) if parts else None


# --- Deal lookup --------------------------------------------------------------------


def _match_by_name(records: list[dict], query: str) -> list[dict]:
    q = query.strip().lower()
    exact = [r for r in records if record_name(r).strip().lower() == q]
    if exact:
        return exact
    return [r for r in records if q in record_name(r).strip().lower()]


def find_target_record(
    token: str, object_slug: str, deal_query: str
) -> tuple[dict | None, str, int]:
    """Returns (record_or_None, how, records_considered).

    how is "id", "name", "ambiguous", or "not_found". On "ambiguous", the
    caller should treat the returned dict's absence as a signal to print the
    match list from a second lookup -- see main(), which re-runs the name
    match to get the full candidate list when this returns "ambiguous".
    """
    if UUID_RE.match(deal_query.strip()):
        rec = fetch_record_by_id(token, object_slug, deal_query.strip())
        if rec is not None:
            return rec, "id", 1

    sample = fetch_records(token, object_slug, full=False)
    matches = _match_by_name(sample, deal_query)
    considered = len(sample)
    if len(matches) == 1:
        return matches[0], "name", considered
    if len(matches) > 1:
        return None, "ambiguous", considered

    full = fetch_records(token, object_slug, full=True)
    matches = _match_by_name(full, deal_query)
    considered = len(full)
    if len(matches) == 1:
        return matches[0], "name", considered
    if len(matches) > 1:
        return None, "ambiguous", considered
    return None, "not_found", considered


# --- Deal Header field resolution ---------------------------------------------------


@dataclass
class HeaderField:
    label: str
    status: str  # "found" | "empty" | "not_tracked"
    detail: str  # human-readable value(s) + source attribute, or an explanation


def resolve_header_fields(attrs: list[dict], record: dict) -> list[HeaderField]:
    fields: list[HeaderField] = []
    for label, keywords in HEADER_FIELD_SPECS:
        matches = find_attributes(attrs, keywords)
        if not matches:
            fields.append(
                HeaderField(label, "not_tracked", "No matching field detected in this workspace's schema.")
            )
            continue

        found_values = []
        empty_titles = []
        for attr in matches:
            slug = attr.get("api_slug")
            title = attr.get("title") or slug
            raw = (record.get("values") or {}).get(slug) or []
            formatted = format_active_values(raw)
            if formatted:
                found_values.append(f"{formatted} (from `{title}`)")
            else:
                empty_titles.append(f"`{title}`")

        if found_values:
            fields.append(HeaderField(label, "found", "; ".join(found_values)))
        else:
            titles = ", ".join(empty_titles[:3])
            fields.append(
                HeaderField(label, "empty", f"Field(s) {titles} exist on this object but are empty on this record.")
            )
    return fields


# --- Rendering -----------------------------------------------------------------------


def render(
    ws: dict,
    meta: dict,
    record: dict,
    header_fields: list[HeaderField],
    notes: list[dict],
    token: str,
) -> str:
    name = ws.get("workspace_name", "Unknown")
    slug = ws.get("workspace_slug", "")
    deal_name = record_name(record)
    record_id = (record.get("id") or {}).get("record_id") or "?"

    out: list[str] = []
    out.append(f"# Attio VC IC Memo Prep: {deal_name}")
    out.append("")
    out.append(f"**Workspace:** `{slug}` &nbsp;·&nbsp; **Run:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    out.append("")
    out.append(meta["detection_note"])
    out.append(f"**Deal record:** `{record_id}` (matched by {meta['matched_by']}, {meta['considered']} record(s) considered).")
    out.append("")
    out.append(
        "This is raw material only -- structured fields pulled from Attio plus every linked "
        "Note's full chronological text. It does **not** classify note content into Market / "
        "Team / Product-Traction / Business Model / Risks sections, and does not draft an "
        "Investment Thesis -- see `SKILL.md` for how Claude should organize this material and "
        "why those steps are deliberately left out of this script."
    )
    out.append("")
    out.append("---")
    out.append("")
    out.append("## Deal Header (from Attio)")
    out.append("")
    out.append("| Field | Status | Detail |")
    out.append("|---|---|---|")
    for f in header_fields:
        status_label = {"found": "Found", "empty": "Empty on this record", "not_tracked": "Not tracked"}[f.status]
        out.append(f"| {f.label} | {status_label} | {f.detail} |")
    out.append("")

    out.append("---")
    out.append("")
    out.append(f"## Notes (raw, chronological) -- {len(notes)} note(s)")
    out.append("")
    if not notes:
        out.append("No Notes linked to this record.")
    else:
        for n in notes:
            created = n.get("created_at") or "unknown date"
            title = n.get("title") or "Untitled"
            out.append(f"### {created} -- {title}")
            out.append("")
            out.append(full_note_text(token, n))
            out.append("")

    out.append("---")
    out.append("")
    out.append(
        "Generated by [5050-vc-skills](https://github.com/NachoLafuente/5050-vc-skills). "
        "Open source from [5050Growth](https://5050growth.com)."
    )
    return "\n".join(out)


def render_json(ws: dict, meta: dict, record: dict, header_fields: list[HeaderField], notes: list[dict], token: str) -> str:
    return json.dumps(
        {
            "workspace": {
                "name": ws.get("workspace_name"),
                "slug": ws.get("workspace_slug"),
                "id": ws.get("workspace_id"),
            },
            "object": {"slug": meta["object_slug"], "label": meta["object_label"], "detection": meta["detection_note"]},
            "deal": {
                "record_id": (record.get("id") or {}).get("record_id"),
                "name": record_name(record),
                "matched_by": meta["matched_by"],
                "records_considered": meta["considered"],
            },
            "deal_header_fields": [
                {"field": f.label, "status": f.status, "detail": f.detail} for f in header_fields
            ],
            "notes": [
                {
                    "note_id": (n.get("id") or {}).get("note_id"),
                    "title": n.get("title"),
                    "created_at": n.get("created_at"),
                    "text": full_note_text(token, n),
                }
                for n in notes
            ],
            "notes_count": len(notes),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        indent=2,
    )


def main() -> int:
    p = argparse.ArgumentParser(
        description="Pull Deal Header fields + raw chronological notes for one deal from a VC/PE fund's Attio workspace"
    )
    p.add_argument("--token", help="Attio API token (default: $ATTIO_API_KEY or $ATTIO_OAUTH2)")
    p.add_argument("--deal", required=True, help="Deal name (exact or partial) or Attio record ID")
    p.add_argument("--object", help="Explicit deal/investment object slug. Overrides auto-detection.")
    p.add_argument("--json", action="store_true", help="Output JSON instead of markdown")
    args = p.parse_args()

    token = args.token or os.environ.get("ATTIO_API_KEY") or os.environ.get("ATTIO_OAUTH2")
    if not token:
        print("error: provide --token or set ATTIO_API_KEY", file=sys.stderr)
        return 2

    try:
        ws = fetch_self(token)
    except requests.HTTPError as e:
        print(f"error: auth failed (HTTP {e.response.status_code}). Token invalid or revoked.", file=sys.stderr)
        return 2

    objects = fetch_objects(token)

    if args.object:
        object_slug = args.object
        matched = next((o for o in objects if o.get("api_slug") == object_slug), None)
        object_label = (matched.get("singular_noun") if matched else None) or object_slug.title()
        detection_note = f"Using object `{object_slug}` (explicit `--object` override)."
    else:
        detected, candidates = detect_deal_object(objects)
        if not detected:
            hint = f" Candidates seen: {', '.join(candidates)}." if candidates else ""
            print(
                "error: could not confidently identify a deal/investment object in this "
                f"workspace's schema.{hint} Re-run with --object <slug>.",
                file=sys.stderr,
            )
            return 2
        object_slug = detected.get("api_slug")
        object_label = detected.get("singular_noun") or object_slug.title()
        detection_note = f"Auto-detected deal object: `{object_slug}` ({object_label})."

    try:
        attrs = fetch_attributes(token, object_slug)
    except requests.HTTPError as e:
        status = getattr(e.response, "status_code", "?")
        print(f"error: could not read attributes for object '{object_slug}' (HTTP {status}).", file=sys.stderr)
        return 2

    try:
        record, how, considered = find_target_record(token, object_slug, args.deal)
    except requests.HTTPError as e:
        status = getattr(e.response, "status_code", "?")
        print(f"error: could not read records for object '{object_slug}' (HTTP {status}).", file=sys.stderr)
        return 2

    if how == "ambiguous":
        # Re-run the name match (sample, then full if needed) just to print candidates.
        sample = fetch_records(token, object_slug, full=False)
        matches = _match_by_name(sample, args.deal)
        if not matches:
            full = fetch_records(token, object_slug, full=True)
            matches = _match_by_name(full, args.deal)
        names = "; ".join(f"{record_name(r)} (`{(r.get('id') or {}).get('record_id')}`)" for r in matches[:10])
        print(
            f"error: '{args.deal}' matches {len(matches)} records, ambiguous: {names}. "
            "Re-run with the exact record ID instead.",
            file=sys.stderr,
        )
        return 2

    if how == "not_found" or record is None:
        print(
            f"error: no deal matching '{args.deal}' found on object '{object_slug}' "
            f"({considered} record(s) scanned). Check spelling, or pass the exact record ID.",
            file=sys.stderr,
        )
        return 2

    try:
        notes = fetch_record_notes(token, object_slug, (record.get("id") or {}).get("record_id"))
    except requests.HTTPError as e:
        status = getattr(e.response, "status_code", "?")
        print(f"error: could not read Notes for this record (HTTP {status}).", file=sys.stderr)
        return 2

    header_fields = resolve_header_fields(attrs, record)

    meta = {
        "object_slug": object_slug,
        "object_label": object_label,
        "detection_note": detection_note,
        "matched_by": how,
        "considered": considered,
    }

    if args.json:
        print(render_json(ws, meta, record, header_fields, notes, token))
    else:
        print(render(ws, meta, record, header_fields, notes, token))
    return 0


if __name__ == "__main__":
    sys.exit(main())

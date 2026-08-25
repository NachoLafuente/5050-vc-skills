"""
Attio backend for attio-vc-coinvestor-map.

Detects the deal/investment object the same "detect, don't hardcode" way as
the sibling skill attio-vc-ic-pipeline-prep, then scans EVERY record on it
(pipeline and portfolio both -- no stage filtering, unlike the sibling skill
attio-vc-portfolio-health in this same repo) for a co-investor/syndicate
attribute, matched by keyword against attribute titles regardless of
declared attribute type. That attribute could be a genuine record-reference
(multiple linked Investor-type records) or a plain text/multi-select field
-- both are handled by the same duck-typed value formatter, since the value
SHAPE at read time tells you which one it is more reliably than the
declared type string does.

Self-contained (own copy of object detection, own HTTP calls) rather than
importing the sibling skill's _common.py -- same convention as
attio-vc-ic-memo-prep and attio-vc-portfolio-health's own _attio.py in this
repo, so every skill folder stays independently copy-able.

Record-reference values are NOT resolved to a target record's name (no
extra GET per reference) -- same convention this repo already established
in attio-vc-ic-memo-prep's `_format_single_value`, which formats a
record-reference as a short id fragment rather than spending a call to
resolve it. See SKILL.md's Limitations section.

Read-only: GET and POST-query calls only. No PATCH, PUT, or POST-write calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from _common import DealRecord, field_title_matches

API_BASE = "https://api.attio.com/v2"
SAMPLE_LIMIT = 500
ATTIO_PAGE_MAX = 500
HTTP_TIMEOUT = 30

DEAL_OBJECT_KEYWORDS = ["deal", "investment", "opportunit", "portfolio compan", "pipeline"]


class DetectionError(Exception):
    pass


def call(token: str, method: str, path: str, body: dict | None = None) -> Any:
    url = f"{API_BASE}{path}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.request(method, url, headers=headers, json=body, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


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


def find_coinvestor_attributes(attrs: list[dict]) -> list[dict]:
    matches = []
    for attr in attrs:
        title = attr.get("title") or attr.get("api_slug") or ""
        if field_title_matches(title):
            matches.append(attr)
    return matches


def record_name(record: dict) -> str:
    values = (record.get("values") or {}).get("name") or []
    if isinstance(values, list) and values:
        entry = values[0]
        if isinstance(entry, dict):
            for key in ("value", "full_name", "domain", "email_address"):
                if entry.get(key):
                    return str(entry[key])
    rid = (record.get("id") or {}).get("record_id") or "?"
    return f"(unnamed {rid[:8]})"


def _current_entries(entries: list) -> list[dict]:
    """Currently-active entries (active_until is None) in a historicized
    Attio value array -- the several simultaneously-selected values for a
    multiselect/multi-record-reference attribute. Falls back to the raw list
    if nothing carries that marker (same tolerant pattern as the sibling
    memo-prep skill's current_entries()).
    """
    dicts = [e for e in entries if isinstance(e, dict)]
    current = [e for e in dicts if e.get("active_until") is None]
    return current if current else dicts


def _format_single_name(entry: dict) -> str | None:
    if entry.get("value") is not None:
        return str(entry["value"])
    option = entry.get("option")
    if isinstance(option, dict) and option.get("title"):
        return str(option["title"])
    status = entry.get("status")
    if isinstance(status, dict) and status.get("title"):
        return str(status["title"])
    if entry.get("full_name"):
        return str(entry["full_name"])
    if entry.get("domain"):
        return str(entry["domain"])
    target_id = entry.get("target_record_id")
    if target_id:
        # Deliberately not resolved to a name -- see module docstring.
        return f"(linked record {str(target_id)[:8]})"
    return None


def extract_coinvestor_names(record: dict, attr_slugs: list[str]) -> list[str]:
    names: list[str] = []
    values = record.get("values") or {}
    for slug in attr_slugs:
        entries = values.get(slug) or []
        for entry in _current_entries(entries):
            name = _format_single_name(entry)
            if name:
                names.append(name)
    return names


@dataclass
class LoadResult:
    detection_note: str
    scope_note: str
    field_note: str | None  # None means "not tracked"
    deals: list[DealRecord]


def load(token: str, object_arg: str | None, full: bool) -> LoadResult:
    objects = fetch_objects(token)

    if object_arg:
        matched = next((o for o in objects if o.get("api_slug") == object_arg), None)
        if matched is None:
            raise DetectionError(f"object '{object_arg}' not found in this workspace's schema.")
        deal_obj = matched
        src_note = f"Using object `{object_arg}` (explicit `--object` override)."
    else:
        deal_obj, candidates = detect_deal_object(objects)
        if deal_obj is None:
            hint = f" Candidates seen: {', '.join(candidates)}." if candidates else ""
            raise DetectionError(
                f"could not confidently identify a deal/investment object in this workspace's "
                f"schema.{hint} Re-run with --object <slug>."
            )
        src_note = f"Auto-detected deal object: `{deal_obj.get('api_slug')}` ({deal_obj.get('singular_noun') or deal_obj.get('api_slug')})."

    object_slug = deal_obj.get("api_slug")
    attrs = fetch_attributes(token, object_slug)
    coinvestor_attrs = find_coinvestor_attributes(attrs)

    records = fetch_records(token, object_slug, full=full)
    scope_note = "all records" if full else f"up to {SAMPLE_LIMIT}-record sample"

    if not coinvestor_attrs:
        return LoadResult(detection_note=src_note, scope_note=scope_note, field_note=None, deals=[])

    attr_slugs = [a.get("api_slug") for a in coinvestor_attrs if a.get("api_slug")]
    labels = ", ".join(f"`{a.get('title') or a.get('api_slug')}`" for a in coinvestor_attrs)

    deals = []
    for r in records:
        rid = (r.get("id") or {}).get("record_id") or ""
        deals.append(DealRecord(key=rid, name=record_name(r), names=extract_coinvestor_names(r, attr_slugs)))

    detection_note = f"{src_note} Co-investor field(s) matched: {labels}."
    return LoadResult(detection_note=detection_note, scope_note=scope_note, field_note=labels, deals=deals)

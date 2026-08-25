"""
Attio backend for attio-vc-portfolio-health.

Detects the portfolio company set two ways, same "detect, don't hardcode"
approach as the sibling skill attio-vc-ic-pipeline-prep:

1. Prefer a DISTINCT object whose name keyword-matches "portfolio" or
   "holding" (and isn't the same object detected as the general deal
   pipeline) -- if a fund's workspace already separates "Deal Flow" from
   "Portfolio", every record in that dedicated object counts, no stage
   filtering needed.
2. Otherwise, fall back to the same deal/investment/opportunity object the
   sibling skill detects, and filter it down to records whose CURRENT stage
   is a closed/invested-style status (the exact set the sibling skill's
   classify_closed_statuses excludes for its own purposes -- here that
   excluded set, minus anything that reads as a LOSS rather than a WIN, is
   the target).

This file is deliberately self-contained (own copy of object/attribute
detection, its own HTTP calls) rather than importing from the sibling
skill's _common.py -- same convention as attio-vc-ic-memo-prep, so every
skill folder in this repo stays independently copy-able. See that skill's
SKILL.md ("Why this script doesn't share code with the sibling skill") for
the rationale.

Read-only: GET and POST-query calls only. No PATCH, PUT, or POST-write calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

from _common import CompanyRecord, Note

API_BASE = "https://api.attio.com/v2"
SAMPLE_LIMIT = 500
ATTIO_PAGE_MAX = 500
HTTP_TIMEOUT = 30

# Attio's /notes endpoint caps `limit` at 50 (confirmed against the public
# OpenAPI spec -- see the sibling skill's _common.py for the same note).
NOTES_PAGE_LIMIT = 50
NOTES_SAMPLE_PAGES = 10  # sample mode: up to 500 notes (10 pages x 50)

DEAL_OBJECT_KEYWORDS = ["deal", "investment", "opportunit", "portfolio compan", "pipeline"]
PORTFOLIO_OBJECT_KEYWORDS = ["portfolio", "holding"]
STAGE_ATTR_KEYWORDS = ["stage", "status", "pipeline stage", "deal stage"]

# Split, unlike the sibling skill's single CLOSED_KEYWORDS list, because here
# won/invested vs lost/passed needs to be told apart -- the sibling only
# needed "closed vs active", not "won vs lost". LOST_KEYWORDS is checked
# first so a title like "Closed Lost" (which also matches "closed") is never
# misclassified as invested just because it isn't currently active. "not
# pursu" (covers "Not Pursued" / "Not Pursuing") is in this list for the same
# reason -- a status like "Closed - Not Pursued" matches "closed" but is a
# passed/rejected deal, not an investment; bare substring matching on
# INVESTED_KEYWORDS alone would misclassify it without this entry.
LOST_KEYWORDS = ["lost", "pass", "declin", "dead", "reject", "withdraw", "abandon", "not pursu"]
INVESTED_KEYWORDS = ["invested", "portfolio", "won", "closed"]

# Candidate keys Attio might use for a note's inline content -- same set the
# sibling memo-prep skill checks. This module does NOT make a per-note GET
# fallback the way ic_memo_prep.py does for its single-deal case -- scanning
# a whole portfolio's notes for keywords is cheap enough with whatever
# content the /notes list response already carries inline, and adding one
# GET per note across an entire portfolio would multiply calls exactly the
# way this repo's Affinity backend is built to avoid. See SKILL.md's
# Limitations section.
NOTE_CONTENT_KEYS = ("content_plaintext", "content_markdown", "content", "plaintext", "markdown", "text", "body")


class DetectionError(Exception):
    """Raised when the portfolio set can't be confidently identified."""


def call(token: str, method: str, path: str, body: dict | None = None) -> Any:
    url = f"{API_BASE}{path}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.request(method, url, headers=headers, json=body, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def parse_dt(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_self(token: str) -> dict:
    return call(token, "GET", "/self")


def fetch_objects(token: str) -> list[dict]:
    return call(token, "GET", "/objects").get("data", [])


def fetch_attributes(token: str, object_slug: str) -> list[dict]:
    return call(token, "GET", f"/objects/{object_slug}/attributes").get("data", [])


def fetch_statuses(token: str, object_slug: str, attribute_slug: str) -> list[dict]:
    return call(token, "GET", f"/objects/{object_slug}/attributes/{attribute_slug}/statuses").get("data", [])


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


def fetch_notes(token: str, object_slug: str, full: bool = False) -> list[dict]:
    notes: list[dict] = []
    offset = 0
    pages = 0
    while True:
        path = f"/notes?parent_object={object_slug}&limit={NOTES_PAGE_LIMIT}&offset={offset}"
        page = call(token, "GET", path).get("data", [])
        notes.extend(page)
        pages += 1
        if len(page) < NOTES_PAGE_LIMIT:
            break
        offset += NOTES_PAGE_LIMIT
        if not full and pages >= NOTES_SAMPLE_PAGES:
            break
    return notes


def extract_note_text(note: dict) -> str:
    for key in NOTE_CONTENT_KEYS:
        val = note.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return ""


def _matches_keyword(haystack: str, keyword: str) -> bool:
    return re.search(r"\b" + re.escape(keyword) + r"s?\b", haystack) is not None


def _object_haystack(obj: dict) -> str:
    slug = (obj.get("api_slug") or "").lower()
    singular = (obj.get("singular_noun") or "").lower()
    plural = (obj.get("plural_noun") or "").lower()
    return f"{slug} {singular} {plural}".replace("_", " ")


def detect_deal_object(objects: list[dict]) -> tuple[dict | None, list[str]]:
    candidates: list[tuple[int, dict]] = []
    for obj in objects:
        haystack = _object_haystack(obj)
        if (obj.get("api_slug") or "").lower() == "deals":
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


def detect_portfolio_object(objects: list[dict], exclude_slug: str | None) -> dict | None:
    """A DISTINCT object (not the general deal object) whose name matches
    portfolio/holding keywords. None if nothing matches, or if the only
    match IS the deal object itself (that's the "same object, filter by
    stage" case, handled by the caller instead).
    """
    candidates: list[tuple[int, dict]] = []
    for obj in objects:
        slug = (obj.get("api_slug") or "").lower()
        if slug == (exclude_slug or "").lower():
            continue
        haystack = _object_haystack(obj)
        score = sum(10 for kw in PORTFOLIO_OBJECT_KEYWORDS if kw in haystack)
        if score:
            candidates.append((score, obj))
    candidates.sort(key=lambda c: -c[0])
    if not candidates:
        return None
    if len(candidates) == 1 or candidates[0][0] > candidates[1][0]:
        return candidates[0][1]
    return None  # ambiguous -- fall back to stage-filtered deal object


def find_attributes(attrs: list[dict], keywords: list[str], attr_type: str | None = None) -> list[dict]:
    matches = []
    for attr in attrs:
        if attr_type and attr.get("type") != attr_type:
            continue
        slug = (attr.get("api_slug") or "").lower()
        title = (attr.get("title") or "").lower()
        haystack = f"{slug} {title}".replace("_", " ").replace("-", " ")
        if any(_matches_keyword(haystack, kw) for kw in keywords):
            matches.append(attr)
    return matches


def find_stage_attribute(attrs: list[dict]) -> dict | None:
    status_attrs = [a for a in attrs if a.get("type") == "status"]
    if not status_attrs:
        return None
    keyword_matches = find_attributes(status_attrs, STAGE_ATTR_KEYWORDS)
    if keyword_matches:
        return keyword_matches[0]
    if len(status_attrs) == 1:
        return status_attrs[0]
    return None


def classify_invested_statuses(statuses: list[dict]) -> set[str]:
    """The flip of the sibling skill's classify_closed_statuses: here we want
    exactly the closed/invested-style statuses, not everything-but-those --
    and specifically the WON side of closed, not the lost/passed side.
    LOST_KEYWORDS is checked first so "Closed Lost" (which also contains
    "closed") never gets counted as invested.
    """
    invested: set[str] = set()
    for s in statuses:
        title = s.get("title") or ""
        low = title.lower()
        if any(kw in low for kw in LOST_KEYWORDS):
            continue
        if any(kw in low for kw in INVESTED_KEYWORDS):
            invested.add(title)
    return invested


def current_status_title(record: dict, attr_slug: str) -> str | None:
    entries = (record.get("values") or {}).get(attr_slug) or []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("active_until") is None:
            status = entry.get("status")
            if isinstance(status, dict):
                return status.get("title")
    return None


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


@dataclass
class LoadResult:
    detection_note: str
    scope_note: str
    companies: list[CompanyRecord]


def load(
    token: str,
    object_arg: str | None,
    full: bool,
    invested_titles_override: set[str] | None = None,
) -> LoadResult:
    """Detect the portfolio set and return normalized CompanyRecords with
    their Notes attached. Raises DetectionError on anything unrecoverable
    (mirrors the sibling skill's "exit 2 with a clear message" pattern --
    the caller in portfolio_health.py catches this and does exactly that).

    `invested_titles_override`, when given (from a human-confirmed
    `.vc-skills-config/<workspace-slug>.json`), replaces the keyword-guessed
    invested/closed-won status set on the stage-filtered fallback path --
    see `_load_stage_filtered`. Has no effect on the distinct-object path,
    which never guesses a status classification in the first place.
    """
    objects = fetch_objects(token)

    if object_arg:
        matched = next((o for o in objects if o.get("api_slug") == object_arg), None)
        if matched is None:
            raise DetectionError(f"object '{object_arg}' not found in this workspace's schema.")
        return _load_stage_filtered(token, matched, full, explicit=True, invested_titles_override=invested_titles_override)

    deal_obj, deal_candidates = detect_deal_object(objects)
    portfolio_obj = detect_portfolio_object(objects, deal_obj.get("api_slug") if deal_obj else None)

    if portfolio_obj is not None:
        return _load_distinct_object(token, portfolio_obj, full)

    if deal_obj is None:
        hint = f" Candidates seen: {', '.join(deal_candidates)}." if deal_candidates else ""
        raise DetectionError(
            "could not confidently identify a deal/investment or portfolio object in this "
            f"workspace's schema.{hint} Re-run with --object <slug>."
        )
    return _load_stage_filtered(token, deal_obj, full, explicit=False, invested_titles_override=invested_titles_override)


def _load_distinct_object(token: str, obj: dict, full: bool) -> LoadResult:
    object_slug = obj.get("api_slug")
    object_label = obj.get("singular_noun") or object_slug.title()
    records = fetch_records(token, object_slug, full=full)
    notes = fetch_notes(token, object_slug, full=full)
    companies = _build_companies(records, notes)
    detection_note = (
        f"Auto-detected a distinct portfolio object: `{object_slug}` ({object_label}). "
        "All records in this object are treated as portfolio companies -- no stage filtering "
        "applied, since being in a dedicated portfolio object already implies invested."
    )
    scope_note = "all records" if full else f"up to {SAMPLE_LIMIT}-record sample"
    return LoadResult(detection_note=detection_note, scope_note=scope_note, companies=companies)


def _load_stage_filtered(
    token: str,
    obj: dict,
    full: bool,
    explicit: bool,
    invested_titles_override: set[str] | None = None,
) -> LoadResult:
    object_slug = obj.get("api_slug")
    object_label = obj.get("singular_noun") or object_slug.title()
    attrs = fetch_attributes(token, object_slug)
    stage_attr = find_stage_attribute(attrs)
    if stage_attr is None:
        raise DetectionError(
            f"no distinct portfolio object found, and object `{object_slug}` has no clear "
            "pipeline-stage (status-type) attribute to filter on for invested/closed-won deals. "
            "Re-run with --object if a different object holds your portfolio."
        )
    stage_slug = stage_attr.get("api_slug")
    stage_label = stage_attr.get("title") or stage_slug

    if invested_titles_override:
        # Human-confirmed via .vc-skills-config -- skip the keyword guess and
        # the /attributes/.../statuses call it would otherwise need.
        invested_titles = set(invested_titles_override)
        classification_src = "cached config"
    else:
        statuses = fetch_statuses(token, object_slug, stage_slug)
        invested_titles = classify_invested_statuses(statuses)
        classification_src = "auto-detected"

    if not invested_titles:
        raise DetectionError(
            f"stage attribute `{stage_label}` on `{object_slug}` has no status option that reads as "
            "invested/closed-won/portfolio (checked against: invested, portfolio, won, closed -- "
            "excluding anything reading as lost/passed). Cannot identify the portfolio set. This "
            "workspace's status names may not match this tool's keyword conventions."
        )

    records = fetch_records(token, object_slug, full=full)
    portfolio_records = [r for r in records if current_status_title(r, stage_slug) in invested_titles]
    notes = fetch_notes(token, object_slug, full=full)
    companies = _build_companies(portfolio_records, notes)

    src = "explicit `--object` override" if explicit else "auto-detected deal/investment object"
    detection_note = (
        f"No distinct portfolio object found; using {src} `{object_slug}` ({object_label}), filtered "
        f"to records whose `{stage_label}` is one of ({classification_src}): "
        f"{', '.join(sorted(invested_titles))}."
    )
    scope_note = (
        f"{len(portfolio_records)} portfolio-stage of {len(records)} scanned "
        f"({'all records' if full else f'up to {SAMPLE_LIMIT}-record sample'})"
    )
    return LoadResult(detection_note=detection_note, scope_note=scope_note, companies=companies)


def _build_companies(records: list[dict], notes: list[dict]) -> list[CompanyRecord]:
    notes_by_record: dict[str, list[Note]] = {}
    for n in notes:
        rid = n.get("parent_record_id")
        if not rid:
            continue
        notes_by_record.setdefault(rid, []).append(
            Note(
                title=n.get("title") or "",
                content=extract_note_text(n),
                created_at=parse_dt(n.get("created_at")),
            )
        )

    companies = []
    for r in records:
        rid = (r.get("id") or {}).get("record_id") or ""
        companies.append(
            CompanyRecord(key=rid, name=record_name(r), notes=notes_by_record.get(rid, []))
        )
    return companies

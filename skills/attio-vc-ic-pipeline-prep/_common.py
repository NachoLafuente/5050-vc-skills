"""
Shared internals for attio-vc-ic-pipeline-prep: Attio API access, deal-object
detection, stage/attribute detection, and generic record helpers used by both
halves of this skill -- the hygiene grade in _hygiene.py and the movement
digest in _movement.py.

Before the merge, attio-vc-pipeline-audit and attio-vc-pipeline-movement were
each fully self-contained (deliberately duplicated code, zero shared imports)
so either could be copied out and run on its own. That property doesn't
matter once both logics live in one skill folder behind one entry point, so
the object-detection / stage-detection / record-helper functions that used to
be duplicated verbatim in both files now live here once. The scoring and
movement-detection logic itself (in _hygiene.py / _movement.py) is unchanged
from the original two scripts.

One deliberate behavior change from the merge: ic_pipeline_prep.py fetches
records, stage statuses, and Notes ONCE and shares the result across both
halves, instead of each half independently paginating /notes and re-fetching
/attributes/.../statuses the way the two standalone scripts used to. Same
data, same detection logic, half the API calls per run.

Read-only: every function in this file makes GET or POST-query calls only.
No PATCH, PUT, or POST-write calls appear anywhere in this skill.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import requests

API_BASE = "https://api.attio.com/v2"
SAMPLE_LIMIT = 500
ATTIO_PAGE_MAX = 500
HTTP_TIMEOUT = 30

# Attio's /notes endpoint caps `limit` at 50 (records/lists allow up to 500).
# Confirmed against the public OpenAPI spec (api.attio.com/openapi/api) --
# mixing this up with ATTIO_PAGE_MAX silently truncates every notes page.
NOTES_PAGE_LIMIT = 50
NOTES_SAMPLE_PAGES = 10  # sample mode: up to 500 notes (10 pages x 50)

# Object-detection keywords: matched as loose substrings against
# api_slug/singular_noun/plural_noun, since these are already short,
# controlled identifiers and workspaces commonly pluralize or compound them
# ("deal", "deals", "portfolio_company", "portfolio_companies").
DEAL_OBJECT_KEYWORDS = ["deal", "investment", "opportunit", "portfolio compan", "pipeline"]

STAGE_ATTR_KEYWORDS = ["stage", "status", "pipeline stage", "deal stage"]

# Status-title keywords for "this pipeline stage is closed/inactive", matched
# as substrings against human-written status titles (e.g. "pass" should match
# "Passed", "Passed - not a fit"). Deliberately not word-boundary here.
CLOSED_KEYWORDS = [
    "closed",
    "won",
    "lost",
    "pass",
    "declin",
    "dead",
    "reject",
    "invested",
    "portfolio",
    "exit",
    "withdraw",
    "abandon",
]


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


# --- API helpers --------------------------------------------------------------


def fetch_self(token: str) -> dict:
    return call(token, "GET", "/self")


def fetch_objects(token: str) -> list[dict]:
    return call(token, "GET", "/objects").get("data", [])


def fetch_attributes(token: str, object_slug: str) -> list[dict]:
    return call(token, "GET", f"/objects/{object_slug}/attributes").get("data", [])


def fetch_statuses(token: str, object_slug: str, attribute_slug: str) -> list[dict]:
    return call(token, "GET", f"/objects/{object_slug}/attributes/{attribute_slug}/statuses").get(
        "data", []
    )


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
    """Raw Note records for object_slug, in whatever scan order Attio's /notes
    endpoint returns them in.

    Fetched once per run and shared: _hygiene.py's interaction-coverage
    dimension only needs the set of parent_record_ids across this list (any
    date); _movement.py's DD/staleness buckets need each note's created_at
    too, to test it against the lookback window. Both derive what they need
    from this same list instead of each half paginating /notes on its own.
    """
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


# --- Deal-object + attribute detection -----------------------------------------


def detect_deal_object(objects: list[dict]) -> tuple[dict | None, list[str]]:
    """Best-guess the deal/investment object. Returns (object, candidate_slugs).

    object is None when detection is not confident enough to act on --
    either nothing matched, or two+ objects tied for the top score.
    """
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
    # Trailing s? tolerates plurals ("Tags", "Sectors") without a full stemmer.
    return re.search(r"\b" + re.escape(keyword) + r"s?\b", haystack) is not None


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
    return None  # multiple status attrs, none keyword-matched: ambiguous


def classify_closed_statuses(statuses: list[dict]) -> set[str]:
    closed: set[str] = set()
    for s in statuses:
        title = s.get("title") or ""
        low = title.lower()
        if any(kw in low for kw in CLOSED_KEYWORDS):
            closed.add(title)
    return closed


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


def active_stage_records(records: list[dict], stage_slug: str, closed_titles: set[str]) -> list[dict]:
    active = []
    for r in records:
        title = current_status_title(r, stage_slug)
        if title is None or title in closed_titles:
            continue
        active.append(r)
    return active


def record_last_touched(record: dict) -> datetime | None:
    """Best-effort 'last modified' for a record.

    Attio does not expose a record-level updated_at. Every attribute value is
    a historical array with active_from/active_until, so the max active_from
    across every attribute's entries is a reasonable proxy for "last time
    anything on this record changed." Falls back to created_at for records
    with no readable value history.
    """
    latest: datetime | None = None
    for entries in (record.get("values") or {}).values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            dt = parse_dt(entry.get("active_from"))
            if dt is None:
                continue
            if latest is None or dt > latest:
                latest = dt
    if latest is None:
        latest = parse_dt(record.get("created_at"))
    return latest


def record_name(record: dict) -> str:
    """Best-effort display name for a record.

    Attio's Record Name attribute is always exposed at api_slug "name"
    regardless of the object's plural/singular noun labels, but the value
    shape varies by the underlying attribute type: text is
    {"value": "..."}, personal-name is {"full_name": "..."}, domain is
    {"domain": "..."}. Falls back to a short record-id fragment when nothing
    is readable, rather than crashing on an unfamiliar shape.
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


# --- Small rendering helpers shared by both report halves -----------------------


def grade_letter(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def bar(score: int, max_score: int, width: int = 20) -> str:
    filled = round((score / max_score) * width) if max_score else 0
    return "█" * filled + "░" * (width - filled)


def percent_score(pct: float, thresholds: list[tuple[float, int]]) -> int:
    for threshold, points in thresholds:
        if pct >= threshold:
            return points
    return 0


def is_filled(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return bool(value)
    return True

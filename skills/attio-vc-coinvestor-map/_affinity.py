"""
Affinity backend for attio-vc-coinvestor-map.

Ground truth for auth, pagination, and endpoint shapes: a real, working
Affinity-to-Attio migration script and playbook from this team's own prior
client work, cross-checked against the actual cached API responses that
migration produced (client identity scrubbed -- no client or fund name
appears anywhere in this file, only the endpoint shapes themselves) -- see
the sibling skill attio-vc-portfolio-health's `_affinity.py` module
docstring in this repo for the detailed shape citations (auth, /lists,
/fields, /field-values, pagination). This module only adds the piece that
skill doesn't need: /field-values.

THIS IS THE EXPENSIVE PATH. Co-investor tracking lives in a field, and
Affinity has no bulk field-value endpoint -- every lookup is one
`GET /field-values?<organization_id|person_id|opportunity_id>=` call per
entity (verified against cached field-value responses: each row is `{id,
field_id, list_entry_id, entity_type, value_type, entity_id, created_at,
updated_at, value}`, fetched one entity at a time in every real script this
grounding was checked against). A naive "check every deal's co-investor
field" run is exactly how a free diagnostic tool burns a fund's entire
monthly Affinity budget. Accordingly:

- Default sample is small (75 entities, not Attio's 500) unless --full.
- --full ALWAYS requires --yes-i-know here (unlike the sibling skill's
  portfolio-health, which has a cheap all-bulk path when a distinct
  portfolio list exists -- this skill has no such cheap path, since the
  co-investor VALUE itself can only come from /field-values).
- `GET /rate-limit` is called and its remaining budget printed before any
  field-value spend happens, so a fund can see the cost before it's paid.

Detects "deal/investment object(s)" as BOTH the pipeline list and a distinct
portfolio list if both exist (unioned, deduped by entity), matching the task
brief's "across both pipeline and portfolio -- co-investor tracking matters
pre- and post-investment." A fund's LP-fundraising list (money coming IN,
not co-investors going into the fund's own deals) is never picked up here,
since it won't keyword-match deal/portfolio naming.

Read-only: GET calls only. No PATCH, PUT, or POST-write calls anywhere.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any

import requests

from _common import DealRecord, field_title_matches

API_BASE = "https://api.affinity.co"
HTTP_TIMEOUT = 30
PAGE_SIZE = 500

DEFAULT_ENTRY_SAMPLE = 75  # deliberately far below Attio's 500 -- see module docstring

DEAL_OR_PORTFOLIO_LIST_KEYWORDS = [
    "deal",
    "investment",
    "opportunit",
    "portfolio compan",
    "pipeline",
    "portfolio",
    "holding",
]

ENTITY_TYPE_PARAM = {0: "person_id", 1: "organization_id", 8: "opportunity_id"}


class DetectionError(Exception):
    pass


class BudgetGateError(Exception):
    pass


def _auth(key: str) -> tuple[str, str]:
    return ("", key)


def call(key: str, method: str, path: str, params: dict | None = None) -> Any:
    resp = requests.request(method, f"{API_BASE}{path}", auth=_auth(key), params=params, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def fetch_rate_limit(key: str) -> dict:
    return call(key, "GET", "/rate-limit").get("rate", {})


def print_budget(rate: dict) -> None:
    org = rate.get("org_monthly") or {}
    per_min = rate.get("api_key_per_minute") or {}
    print(
        f"Affinity budget: {org.get('used', '?')}/{org.get('limit', '?')} used this month "
        f"({org.get('remaining', '?')} remaining) &nbsp;·&nbsp; {per_min.get('limit', '?')}/min cap.",
        file=sys.stderr,
    )


def fetch_lists(key: str) -> list[dict]:
    return call(key, "GET", "/lists")


def fetch_fields(key: str, list_id: int | None = None) -> list[dict]:
    params = {"list_id": list_id} if list_id is not None else None
    return call(key, "GET", "/fields", params)


def fetch_list_entries(key: str, list_id: int) -> list[dict]:
    """Full pagination -- list-entries themselves are bulk/cheap regardless
    of --full. It's the per-entity field-value lookup afterward that's
    gated, not this call.
    """
    out: list[dict] = []
    token = None
    while True:
        params: dict[str, Any] = {"page_size": PAGE_SIZE}
        if token:
            params["page_token"] = token
        d = call(key, "GET", f"/lists/{list_id}/list-entries", params)
        out.extend(d.get("list_entries", []))
        token = d.get("next_page_token")
        if not token:
            break
    return out


def _matches_keyword(haystack: str, keyword: str) -> bool:
    return re.search(r"\b" + re.escape(keyword) + r"s?\b", haystack) is not None


def detect_deal_lists(lists: list[dict]) -> list[dict]:
    """Every list whose name matches deal/investment/portfolio/holding
    keywords -- a union, not a single best-scoring winner, since co-investor
    tracking spans both a pipeline list and a separate portfolio list when a
    fund has both. See module docstring.
    """
    matched = []
    for lst in lists:
        haystack = (lst.get("name") or "").lower().replace("_", " ")
        if any(_matches_keyword(haystack, kw) for kw in DEAL_OR_PORTFOLIO_LIST_KEYWORDS):
            matched.append(lst)
    return matched


def _entry_name(entry: dict) -> str:
    entity = entry.get("entity") or {}
    if entity.get("name"):
        return str(entity["name"])
    first = entity.get("first_name") or ""
    last = entity.get("last_name") or ""
    full = f"{first} {last}".strip()
    if full:
        return full
    return f"(unnamed entity {entry.get('entity_id', '?')})"


def format_affinity_value(value: Any) -> str | None:
    """Duck-typed formatter for a field-value's `value`, which is not a
    single documented shape (dropdown option, location, text, number, a
    bare person/org id for a reference-type field, or a list of any of
    those for a multi-value field) -- see the sibling portfolio-health
    backend's module docstring for the grounding on why this stays
    defensive rather than branching on `value_type` numbers this repo
    hasn't fully enumerated from a live account.
    """
    if value is None:
        return None
    if isinstance(value, list):
        parts = [p for p in (format_affinity_value(v) for v in value) if p]
        return "; ".join(parts) if parts else None
    if isinstance(value, dict):
        if value.get("text"):
            return str(value["text"])
        if value.get("first_name") or value.get("last_name"):
            return f"{value.get('first_name', '')} {value.get('last_name', '')}".strip()
        if value.get("name"):
            return str(value["name"])
        loc_parts = [value.get(k) for k in ("city", "state", "country") if value.get(k)]
        if loc_parts:
            return ", ".join(str(p) for p in loc_parts)
        return None
    s = str(value).strip()
    return s if s else None


@dataclass
class LoadResult:
    detection_note: str
    scope_note: str
    field_note: str | None  # None means "not tracked"
    deals: list[DealRecord]


def load(key: str, list_arg: str | None, full: bool, sample_size: int | None, yes_i_know: bool) -> LoadResult:
    rate = fetch_rate_limit(key)
    print_budget(rate)

    lists = fetch_lists(key)

    if list_arg:
        target = next((l for l in lists if str(l.get("id")) == list_arg or l.get("name") == list_arg), None)
        if target is None:
            raise DetectionError(f"list '{list_arg}' not found (checked by id and exact name).")
        target_lists = [target]
        src_note = f"Using list `{target.get('name')}` (list {target['id']}, explicit `--list` override)."
    else:
        target_lists = detect_deal_lists(lists)
        if not target_lists:
            raise DetectionError(
                "could not confidently identify a deal/investment or portfolio list in this "
                "Affinity account. Re-run with --list <id-or-name>."
            )
        names = ", ".join(f"`{l.get('name')}`" for l in target_lists)
        src_note = f"Auto-detected deal/portfolio list(s): {names} (unioned, pipeline + portfolio)."

    # Field detection: list-scoped fields on every target list, plus global
    # (account-wide) fields once. Duplicated field_ids across lists are
    # fine -- extract_names dedupes by field_id per entity anyway.
    field_ids: dict[int, str] = {}
    for lst in target_lists:
        for f in fetch_fields(key, list_id=lst["id"]):
            if field_title_matches(f.get("name") or ""):
                field_ids[f["id"]] = f.get("name") or str(f["id"])
    for f in fetch_fields(key):
        if field_title_matches(f.get("name") or ""):
            field_ids[f["id"]] = f.get("name") or str(f["id"])

    # Union entries across all target lists, deduped by (entity_type, entity_id)
    # so an organization present in both a "Deals" and a "Portfolio" list is
    # counted once, not twice.
    entries_by_key: dict[tuple[int, int], dict] = {}
    for lst in target_lists:
        for e in fetch_list_entries(key, lst["id"]):
            et, eid = e.get("entity_type"), e.get("entity_id")
            if et is None or eid is None:
                continue
            entries_by_key.setdefault((et, eid), e)
    all_entries = list(entries_by_key.values())
    scope_note_total = len(all_entries)

    if not field_ids:
        scope_note = f"{scope_note_total} entities found, 0 checked (no matching field)"
        return LoadResult(detection_note=src_note, scope_note=scope_note, field_note=None, deals=[])

    sample_cap = sample_size or DEFAULT_ENTRY_SAMPLE
    if full and not yes_i_know:
        list_names = ", ".join(f"`{l.get('name')}`" for l in target_lists)
        raise BudgetGateError(
            f"--full would call /field-values once per entity across {scope_note_total} entities in "
            f"{list_names} -- Affinity has no bulk field-value endpoint, so this is real per-entity "
            "spend, not a bulk call. Re-run with --yes-i-know to confirm, or drop --full to use the "
            f"default {sample_cap}-entity sample instead."
        )

    entries = all_entries if full else all_entries[:sample_cap]

    deals: list[DealRecord] = []
    for e in entries:
        et = e.get("entity_type")
        param = ENTITY_TYPE_PARAM.get(et)
        if param is None:
            continue
        fvs = call(key, "GET", "/field-values", {param: e.get("entity_id")})
        names: list[str] = []
        for fv in fvs:
            if fv.get("field_id") not in field_ids:
                continue
            formatted = format_affinity_value(fv.get("value"))
            if formatted:
                names.append(formatted)
        deals.append(DealRecord(key=f"{et}:{e.get('entity_id')}", name=_entry_name(e), names=names))

    field_note = ", ".join(f"`{name}`" for name in field_ids.values())
    scope_note = (
        f"{len(deals)} of {scope_note_total} entities checked "
        f"({'all' if full else f'up to {sample_cap}-entity sample'} -- 1 field-value call per entity checked)"
    )
    detection_note = f"{src_note} Co-investor field(s) matched: {field_note}."
    return LoadResult(detection_note=detection_note, scope_note=scope_note, field_note=field_note, deals=deals)

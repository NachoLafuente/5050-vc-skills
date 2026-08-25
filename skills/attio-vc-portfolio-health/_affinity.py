"""
Affinity backend for attio-vc-portfolio-health.

Ground truth for auth, pagination, and endpoint shapes: a real, working
Affinity-to-Attio migration script and playbook from this team's own prior
client work, cross-checked against the actual cached API responses that
migration produced (client identity scrubbed -- no client or fund name
appears anywhere in this file, only the endpoint shapes themselves). Nothing
here is invented past what those sources show:

- Auth: HTTP Basic, empty username, API key as password.
- Base URL: https://api.affinity.co
- `GET /lists` and `GET /fields` return bare JSON arrays (verified against
  the cached `lists.json` / `list_fields.json` from that migration).
- `GET /lists/{id}/list-entries` is wrapped: {"list_entries": [...],
  "next_page_token": ...} -- paginated with `page_size` (max 500) and
  `page_token` (verified against that migration script's own pagination
  helper).
- `GET /rate-limit` is free (exempt from the monthly cap) and returns
  {"rate": {"org_monthly": {limit, remaining, reset, used}, ...}}.
- `GET /notes` (called with NO entity filter) returns every note in the
  account, paginated the same page_size/page_token way. This is inferred by
  analogy to every other Affinity V1 list endpoint following the identical
  wrapper shape (all confirmed above), corroborated by page-count arithmetic
  observed on a real pull (~3,056 notes cached via ~7 pages -- consistent
  with 500/page). Handled defensively below: if the response isn't wrapped
  under "notes", the code falls back to scanning for whatever key holds a
  list. If a workspace's Affinity tenant behaves differently, this will
  surface as an explicit "could not read notes" error, not silent
  mis-parsing.
- Field-value shape: {id, field_id, list_entry_id, entity_type, value_type,
  entity_id, created_at, updated_at, value} -- one call per entity, no bulk
  endpoint (verified against cached `fv_organizations.json`).

Cost profile (why two different code paths below have different budget
guards): a fund with a DISTINCT "Portfolio" list (confirmed real-world case
-- the tenant this was grounded against has exactly this, a list literally
named "[Fund Name] Portfolio") costs nothing beyond bulk list-entries + bulk
notes pagination, both cheap. A fund WITHOUT a distinct portfolio list needs
its single deal list's Status field to tell invested
apart from active/passed -- and Affinity has no bulk field-value endpoint,
so that fallback costs one /field-values call per sampled entry. Only that
fallback path is budget-gated the same way the sibling skill
attio-vc-coinvestor-map gates its (always per-entity) co-investor lookup.

Read-only: GET calls only. No PATCH, PUT, or POST-write calls anywhere.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from _common import CompanyRecord, Note

API_BASE = "https://api.affinity.co"
HTTP_TIMEOUT = 30
PAGE_SIZE = 500

# Cheap path (distinct portfolio list): pagination is bulk regardless of
# size, so this cap is a runtime/predictability courtesy, not a budget
# necessity. Expensive fallback path (stage-filtered deal list): this cap
# gates real per-entity /field-values spend -- see module docstring.
DEFAULT_ENTRY_SAMPLE = 75
NOTES_SAMPLE_PAGES = 10  # up to 5,000 notes by default; --full paginates all

PORTFOLIO_LIST_KEYWORDS = ["portfolio", "holding"]
DEAL_LIST_KEYWORDS = ["deal", "investment", "opportunit", "portfolio compan", "pipeline"]
STATUS_FIELD_KEYWORDS = ["status", "stage"]
# "not pursu" (covers "Not Pursued"/"Not Pursuing") is deliberately included:
# a status like "Closed - Not Pursued" matches "closed" in INVESTED_KEYWORDS
# but is a passed/rejected deal, not an investment. See the Attio backend's
# identical list for the fuller rationale (same fix applied on both platforms).
LOST_KEYWORDS = ["lost", "pass", "declin", "dead", "reject", "withdraw", "abandon", "not pursu"]
INVESTED_KEYWORDS = ["invested", "portfolio", "won", "closed"]

# entity_type in Affinity's list-entries / notes payloads: 0 = Person,
# 1 = Organization, 8 = Opportunity (verified against real list-entries and
# lists.json -- a list of type 1 held organizations with domain/name fields,
# type 0 held persons with first_name/last_name, type 8 held opportunities).
ENTITY_TYPE_PARAM = {0: "person_id", 1: "organization_id", 8: "opportunity_id"}
ENTITY_TYPE_NOTE_KEY = {0: "person_ids", 1: "organization_ids", 8: "opportunity_ids"}


class DetectionError(Exception):
    pass


class BudgetGateError(Exception):
    """Raised when --full is requested on the expensive (per-entity)
    fallback path without --yes-i-know."""


def _auth(key: str) -> tuple[str, str]:
    return ("", key)


def call(key: str, method: str, path: str, params: dict | None = None) -> Any:
    resp = requests.request(method, f"{API_BASE}{path}", auth=_auth(key), params=params, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def parse_dt(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


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


def fetch_list_entries(key: str, list_id: int, full: bool, sample_cap: int) -> list[dict]:
    out: list[dict] = []
    token = None
    while True:
        params: dict[str, Any] = {"page_size": PAGE_SIZE}
        if token:
            params["page_token"] = token
        d = call(key, "GET", f"/lists/{list_id}/list-entries", params)
        page = d.get("list_entries", [])
        out.extend(page)
        token = d.get("next_page_token")
        if not token:
            break
        if not full and len(out) >= sample_cap:
            out = out[:sample_cap]
            break
    return out


def fetch_notes_bulk(key: str, full: bool) -> list[dict]:
    """Every note in the account, unfiltered, paginated. See module
    docstring for why this is grounded as the cheap way to do cadence
    matching (one bulk pull, grouped locally) instead of one /notes call per
    portfolio company.
    """
    out: list[dict] = []
    token = None
    pages = 0
    while True:
        params: dict[str, Any] = {"page_size": PAGE_SIZE}
        if token:
            params["page_token"] = token
        d = call(key, "GET", "/notes", params)
        if isinstance(d, list):
            page = d
            token = None  # bare-list shape carries no continuation token
        else:
            page = d.get("notes")
            if page is None:
                # Defensive fallback: use the first list-valued field found.
                page = next((v for v in d.values() if isinstance(v, list)), [])
            token = d.get("next_page_token")
        out.extend(page)
        pages += 1
        if not token:
            break
        if not full and pages >= NOTES_SAMPLE_PAGES:
            break
    return out


def _matches_keyword(haystack: str, keyword: str) -> bool:
    return re.search(r"\b" + re.escape(keyword) + r"s?\b", haystack) is not None


def _list_haystack(lst: dict) -> str:
    return (lst.get("name") or "").lower().replace("_", " ")


def detect_portfolio_list(lists: list[dict]) -> dict | None:
    candidates = [(sum(10 for kw in PORTFOLIO_LIST_KEYWORDS if kw in _list_haystack(l)), l) for l in lists]
    candidates = [(s, l) for s, l in candidates if s > 0]
    candidates.sort(key=lambda c: -c[0])
    if not candidates:
        return None
    if len(candidates) == 1 or candidates[0][0] > candidates[1][0]:
        return candidates[0][1]
    return None


def detect_deal_list(lists: list[dict]) -> tuple[dict | None, list[str]]:
    candidates = [(sum(10 for kw in DEAL_LIST_KEYWORDS if kw in _list_haystack(l)), l) for l in lists]
    candidates = [(s, l) for s, l in candidates if s > 0]
    candidates.sort(key=lambda c: -c[0])
    names = [c[1].get("name", "?") for c in candidates]
    if not candidates:
        return None, []
    if len(candidates) == 1 or candidates[0][0] > candidates[1][0]:
        return candidates[0][1], names
    return None, names


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


@dataclass
class LoadResult:
    detection_note: str
    scope_note: str
    companies: list[CompanyRecord]


def load(
    key: str,
    list_arg: str | None,
    full: bool,
    sample_size: int | None,
    yes_i_know: bool,
    invested_titles_override: set[str] | None = None,
) -> LoadResult:
    """`invested_titles_override`, when given (from a human-confirmed
    `.vc-skills-config/<workspace-slug>.json`), replaces the keyword-guessed
    invested/closed-won status set on the stage-filtered fallback path -- see
    `_load_stage_filtered`. It does not reduce the per-entity /field-values
    spend on that path (each sampled entry's *current* status still has to be
    read live), only the semantic guess of which status option TEXTS count
    as invested.
    """
    rate = fetch_rate_limit(key)
    print_budget(rate)

    lists = fetch_lists(key)
    sample_cap = sample_size or DEFAULT_ENTRY_SAMPLE

    if list_arg:
        target = next((l for l in lists if str(l.get("id")) == list_arg or l.get("name") == list_arg), None)
        if target is None:
            raise DetectionError(f"list '{list_arg}' not found (checked by id and exact name).")
        return _load_distinct_list(key, target, full, sample_cap)

    portfolio_list = detect_portfolio_list(lists)
    if portfolio_list is not None:
        return _load_distinct_list(key, portfolio_list, full, sample_cap)

    deal_list, candidates = detect_deal_list(lists)
    if deal_list is None:
        hint = f" Lists seen: {', '.join(candidates)}." if candidates else ""
        raise DetectionError(
            f"could not confidently identify a portfolio or deal/investment list in this Affinity "
            f"account.{hint} Re-run with --list <id-or-name>."
        )
    return _load_stage_filtered(key, deal_list, full, sample_cap, yes_i_know, invested_titles_override)


def _load_distinct_list(key: str, lst: dict, full: bool, sample_cap: int) -> LoadResult:
    list_id = lst["id"]
    entries = fetch_list_entries(key, list_id, full, sample_cap)
    notes = fetch_notes_bulk(key, full)
    companies = _build_companies(entries, notes)
    detection_note = (
        f"Auto-detected a distinct portfolio list: `{lst.get('name')}` (list {list_id}). Every entry "
        "is treated as a portfolio company -- no status filtering needed, since membership in a "
        "dedicated portfolio list already implies invested. This is the cheap path: no per-entity "
        "field-value calls."
    )
    scope_note = "all entries" if full else f"up to {sample_cap}-entry sample"
    return LoadResult(detection_note=detection_note, scope_note=scope_note, companies=companies)


def _load_stage_filtered(
    key: str,
    lst: dict,
    full: bool,
    sample_cap: int,
    yes_i_know: bool,
    invested_titles_override: set[str] | None = None,
) -> LoadResult:
    """No distinct portfolio list exists -- fall back to the deal list's
    Status field. This path costs one /field-values call per sampled entry
    (Affinity has no bulk field-value endpoint), so it's gated the same way
    attio-vc-coinvestor-map gates its co-investor lookup.
    """
    list_id = lst["id"]
    fields = fetch_fields(key, list_id=list_id)
    status_field = None
    for f in fields:
        name_low = (f.get("name") or "").lower()
        if any(_matches_keyword(name_low, kw) for kw in STATUS_FIELD_KEYWORDS):
            status_field = f
            break

    if status_field is None:
        raise DetectionError(
            f"no distinct portfolio list found, and list `{lst.get('name')}` (list {list_id}) has no "
            "Status/Stage field to filter invested deals from active/passed ones. Re-run with --list "
            "if a different Affinity list holds your portfolio."
        )

    if invested_titles_override:
        # Human-confirmed via .vc-skills-config -- skip the keyword guess
        # over this field's dropdown options.
        invested_option_texts = set(invested_titles_override)
        classification_src = "cached config"
    else:
        invested_option_texts = set()
        for opt in status_field.get("dropdown_options") or []:
            title = (opt.get("text") or "")
            low = title.lower()
            if any(kw in low for kw in LOST_KEYWORDS):
                continue
            if any(kw in low for kw in INVESTED_KEYWORDS):
                invested_option_texts.add(title)
        classification_src = "auto-detected"

    if not invested_option_texts:
        raise DetectionError(
            f"Status field `{status_field.get('name')}` on list `{lst.get('name')}` has no dropdown "
            "option that reads as invested/won/closed (checked against: invested, portfolio, won, "
            "closed -- excluding lost/passed). Cannot identify the portfolio set from this list."
        )

    if full and not yes_i_know:
        raise BudgetGateError(
            f"--full on the stage-filtered fallback path calls /field-values once per entry in list "
            f"`{lst.get('name')}` to read its {status_field.get('name')} value -- that is NOT a bulk "
            "call, Affinity has no bulk field-value endpoint. Re-run with --yes-i-know to confirm you "
            "want to spend that budget, or drop --full to use the default "
            f"{sample_cap}-entry sample instead."
        )

    entries = fetch_list_entries(key, list_id, full, sample_cap)
    field_id = status_field["id"]
    kept_entries = []
    for e in entries:
        entity_type = e.get("entity_type")
        param = ENTITY_TYPE_PARAM.get(entity_type)
        if param is None:
            continue
        fvs = call(key, "GET", "/field-values", {param: e.get("entity_id")})
        current_title = None
        for fv in fvs:
            if fv.get("field_id") != field_id:
                continue
            val = fv.get("value")
            text = val.get("text") if isinstance(val, dict) else val
            if text:
                current_title = str(text)
        if current_title in invested_option_texts:
            kept_entries.append(e)

    notes = fetch_notes_bulk(key, full)
    companies = _build_companies(kept_entries, notes)

    detection_note = (
        f"No distinct portfolio list found; using deal/investment list `{lst.get('name')}` (list "
        f"{list_id}), filtered via /field-values (one call per sampled entry) to entries whose "
        f"`{status_field.get('name')}` is one of ({classification_src}): "
        f"{', '.join(sorted(invested_option_texts))}."
    )
    scope_note = (
        f"{len(kept_entries)} portfolio-status of {len(entries)} entries checked "
        f"({'all entries' if full else f'up to {sample_cap}-entry sample'} -- 1 field-value call per "
        "entry checked)"
    )
    return LoadResult(detection_note=detection_note, scope_note=scope_note, companies=companies)


def _build_companies(entries: list[dict], notes: list[dict]) -> list[CompanyRecord]:
    # Index entries by (entity_type, entity_id) since Affinity ids are only
    # unique within a type (a person and an organization can share a raw id).
    keys_by_type: dict[int, set[int]] = {}
    entry_by_key: dict[tuple[int, int], dict] = {}
    for e in entries:
        et, eid = e.get("entity_type"), e.get("entity_id")
        if et is None or eid is None:
            continue
        keys_by_type.setdefault(et, set()).add(eid)
        entry_by_key[(et, eid)] = e

    notes_by_key: dict[tuple[int, int], list[Note]] = {}
    for n in notes:
        created = parse_dt(n.get("created_at"))
        note_obj = Note(title="", content=n.get("content") or "", created_at=created)
        for et, id_key in ENTITY_TYPE_NOTE_KEY.items():
            if et not in keys_by_type:
                continue
            for eid in n.get(id_key) or []:
                if eid in keys_by_type[et]:
                    notes_by_key.setdefault((et, eid), []).append(note_obj)

    companies = []
    for (et, eid), entry in entry_by_key.items():
        companies.append(
            CompanyRecord(
                key=f"{et}:{eid}",
                name=_entry_name(entry),
                notes=notes_by_key.get((et, eid), []),
            )
        )
    return companies

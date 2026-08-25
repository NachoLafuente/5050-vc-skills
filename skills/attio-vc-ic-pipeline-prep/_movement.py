"""
Movement-digest half of attio-vc-ic-pipeline-prep: a written recap of what
moved in the pipeline over a lookback window -- new deals, deals that
advanced a stage, deals gone stale, and DD/activity delta from logged Notes.

This is the detection logic that used to be the whole of
attio-vc-pipeline-movement -- unchanged here except that stage-attribute
detection, closed-status titles, and Notes are now looked up once in
ic_pipeline_prep.py's main() and passed in, instead of this module fetching
its own copy (see _common.py's module docstring for why).

Read-only: this module makes no API calls itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from _common import parse_dt, record_last_touched, record_name

MAX_LIST_ITEMS = 20  # markdown truncates each bucket's list at this many lines


@dataclass
class Bucket:
    name: str
    count: int
    items: list[str] = field(default_factory=list)
    applicable: bool = True
    findings: list[str] = field(default_factory=list)


@dataclass
class DDSection:
    total_notes: int
    zero_count: int
    zero_items: list[str] = field(default_factory=list)
    applicable: bool = True
    findings: list[str] = field(default_factory=list)


def notes_in_window(notes: list[dict], cutoff: datetime) -> tuple[set[str], int]:
    """(record ids with >=1 note in the window, total notes created in the window)."""
    ids: set[str] = set()
    total = 0
    for n in notes:
        dt = parse_dt(n.get("created_at"))
        if dt is None or dt < cutoff:
            continue
        total += 1
        rid = n.get("parent_record_id")
        if rid:
            ids.add(rid)
    return ids, total


# --- Movement detection --------------------------------------------------------


def find_new_deals(records: list[dict], cutoff: datetime) -> tuple[list[str], int]:
    """Records whose created_at falls inside the window, newest first."""
    items: list[tuple[datetime, str]] = []
    for r in records:
        dt = parse_dt(r.get("created_at"))
        if dt is None or dt < cutoff:
            continue
        items.append((dt, f"{record_name(r)} (created {dt.date().isoformat()})"))
    items.sort(key=lambda t: t[0], reverse=True)
    return [line for _, line in items], len(items)


def find_advanced_stage(records: list[dict], stage_slug: str, cutoff: datetime) -> tuple[list[str], int]:
    """Deals whose stage attribute's currently-active value started inside the window.

    A record needs 2+ historical entries on the stage attribute to count -- a
    single entry means the deal has never changed stage (its only-ever status
    was set at creation), which belongs in "new deals", not here. Where the
    entry immediately before the current one is readable, this shows
    from-stage -> to-stage; otherwise it falls back to "moved stage as of
    <date>".
    """
    items: list[tuple[datetime, str]] = []
    for r in records:
        entries = [e for e in ((r.get("values") or {}).get(stage_slug) or []) if isinstance(e, dict)]
        if len(entries) < 2:
            continue
        entries.sort(key=lambda e: e.get("active_from") or "")
        current, previous = entries[-1], entries[-2]
        dt = parse_dt(current.get("active_from"))
        if dt is None or dt < cutoff:
            continue
        to_title = (current.get("status") or {}).get("title") or "?"
        from_title = (previous.get("status") or {}).get("title")
        name = record_name(r)
        if from_title:
            items.append((dt, f"{name}: {from_title} → {to_title} ({dt.date().isoformat()})"))
        else:
            items.append((dt, f"{name}: moved stage as of {dt.date().isoformat()}"))
    items.sort(key=lambda t: t[0], reverse=True)
    return [line for _, line in items], len(items)


def find_stale_deals(
    active_records: list[dict], noted_ids: set[str], cutoff: datetime
) -> tuple[list[str], int]:
    """Active-stage deals with no attribute change and no logged Note in the window.

    "No attribute change" reuses record_last_touched (max active_from across
    every attribute) the same way the hygiene half's stage-gate dimension
    does -- if that's older than the window start, nothing on the record
    moved. This bucket additionally requires zero Notes in the window too,
    since a deal can be worked (a call logged, DD note added) without any
    field on the record itself changing.
    """
    now = datetime.now(timezone.utc)
    items: list[tuple[int, str]] = []
    for r in active_records:
        rid = (r.get("id") or {}).get("record_id")
        if rid and rid in noted_ids:
            continue  # DD activity inside the window -- not stale
        touched = record_last_touched(r)
        if touched is not None and touched >= cutoff:
            continue  # an attribute changed inside the window -- not stale
        if touched is not None:
            days_idle = (now - touched).days
            suffix = f"{days_idle}d since last touch"
        else:
            days_idle = 0
            suffix = "no readable history"
        items.append((days_idle, f"{record_name(r)} ({suffix})"))
    items.sort(key=lambda t: -t[0])
    return [line for _, line in items], len(items)


def find_zero_dd_active(active_records: list[dict], noted_ids: set[str]) -> tuple[list[str], int]:
    """Active-stage deals with zero logged Notes in the window (regardless of field changes)."""
    items = []
    for r in active_records:
        rid = (r.get("id") or {}).get("record_id")
        if rid and rid in noted_ids:
            continue
        items.append(record_name(r))
    return items, len(items)


def build_summary(new_count: int, advanced_count: int, stale_count: int, total_notes: int, days: int) -> str:
    parts = [
        f"{new_count} new deal{'s' if new_count != 1 else ''}",
        f"{advanced_count} advanced a stage",
        f"{stale_count} gone stale",
        f"{total_notes} DD note{'s' if total_notes != 1 else ''} logged",
    ]
    return ", ".join(parts) + f" in the last {days} days."


# --- Rendering (Part 2 of the combined report; no outer H1/header -- "
# ic_pipeline_prep.py supplies the shared workspace header) -------------------


def render_movement(buckets: list[Bucket], dd: DDSection, summary: str, days: int) -> list[str]:
    out: list[str] = []
    out.append(f"## Part 2 -- Pipeline Movement (Last {days} Days)")
    out.append("")
    out.append("### Summary")
    out.append("")
    out.append(summary)
    out.append("")

    for b in buckets:
        tag = " -- not applicable" if not b.applicable else ""
        out.append(f"### {b.name}: {b.count}{tag}")
        out.append("")
        for finding in b.findings:
            out.append(f"- {finding}")
        if b.applicable:
            if not b.items:
                out.append("- None in this window.")
            else:
                shown = b.items[:MAX_LIST_ITEMS]
                out.extend(f"- {line}" for line in shown)
                remainder = len(b.items) - len(shown)
                if remainder > 0:
                    out.append(f"- (+{remainder} more)")
        out.append("")

    tag = " -- not applicable" if not dd.applicable else ""
    out.append(f"### DD / activity delta{tag}")
    out.append("")
    for finding in dd.findings:
        out.append(f"- {finding}")
    if dd.applicable:
        out.append(f"- **{dd.total_notes} note(s) logged in the window.**")
        if dd.zero_items:
            out.append(f"- {dd.zero_count} active deal(s) with zero DD activity in the window:")
            shown = dd.zero_items[:MAX_LIST_ITEMS]
            out.extend(f"  - {line}" for line in shown)
            remainder = len(dd.zero_items) - len(shown)
            if remainder > 0:
                out.append(f"  - (+{remainder} more)")
        else:
            out.append("- Every active deal had at least one DD note logged in the window.")
    out.append("")
    return out


def movement_to_dict(buckets: list[Bucket], dd: DDSection, summary: str, days: int) -> dict:
    return {
        "window_days": days,
        "summary": summary,
        "buckets": [
            {
                "name": b.name,
                "count": b.count,
                "applicable": b.applicable,
                "items": b.items,
                "findings": b.findings,
            }
            for b in buckets
        ],
        "dd_activity": {
            "name": "DD / activity delta",
            "total_notes": dd.total_notes,
            "zero_dd_active_count": dd.zero_count,
            "zero_dd_active_deals": dd.zero_items,
            "applicable": dd.applicable,
            "findings": dd.findings,
        },
    }

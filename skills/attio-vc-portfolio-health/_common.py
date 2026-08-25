"""
Source-agnostic internals for attio-vc-portfolio-health: keyword scanning,
cadence scoring, and markdown/JSON rendering shared by both backends
(_attio.py, _affinity.py).

This module never touches the network. _attio.py and _affinity.py each fetch
their own platform's data and normalize it into the CompanyRecord shape
defined here; everything downstream of that (keyword matching, days-since
math, scoring, rendering) is identical regardless of which CRM the data came
from -- that's the point of splitting it out.

Read-only: no API calls anywhere in this file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Board-meeting and KPI-reporting keyword sets. Matched as whole phrases
# (word-boundary, case-insensitive) against a Note's title + content combined.
# These are intentionally narrow and literal -- see SKILL.md's "never invent"
# section: a fund that logs board notes without ever writing one of these
# phrases will show as 0% covered, and that is a real finding about their
# Attio/Affinity hygiene, not a bug in this tool.
BOARD_KEYWORDS = ["board meeting", "board update", "board deck", "board minutes", "board pack"]
KPI_KEYWORDS = ["kpi", "metrics update", "monthly update", "investor update"]

DEFAULT_BOARD_DAYS = 45
DEFAULT_KPI_DAYS = 30

MAX_TABLE_ROWS = 20  # markdown detail table truncates at this many rows


def _matches_keyword(haystack: str, keyword: str) -> bool:
    # Trailing s? tolerates plurals ("KPIs", "Board Decks") without a stemmer.
    # Multi-word keywords ("board meeting") work fine here too -- \b anchors
    # on the phrase's own start/end, re.escape handles the literal space.
    return re.search(r"\b" + re.escape(keyword) + r"s?\b", haystack) is not None


def text_matches_any(haystack: str, keywords: list[str]) -> bool:
    low = haystack.lower()
    return any(_matches_keyword(low, kw) for kw in keywords)


@dataclass
class Note:
    """One note, already reduced to what this skill needs: title, whatever
    content text was readable without an extra per-note API call, and a
    parsed created_at. Both backends build these directly -- Attio from its
    /notes list response, Affinity from its /notes list response (which
    already carries full content inline, unlike Attio's).
    """

    title: str
    content: str
    created_at: datetime | None


@dataclass
class CompanyRecord:
    """One portfolio company, source-agnostic: a display name plus every
    Note either backend could attribute to it (any date -- filtering to a
    lookback window isn't relevant here, cadence needs the single most
    recent match, however old).
    """

    key: str
    name: str
    notes: list[Note] = field(default_factory=list)


@dataclass
class CadenceRow:
    name: str
    board_last: datetime | None
    board_days: int | None
    board_status: str  # "ok" | "overdue" | "never"
    kpi_last: datetime | None
    kpi_days: int | None
    kpi_status: str  # "ok" | "overdue" | "never"


def most_recent_match(notes: list[Note], keywords: list[str]) -> datetime | None:
    """The most recent created_at among this company's notes whose title or
    content matches any of the given keywords. None if no note ever matched
    (that's the "never" case, distinct from "matched but stale").
    """
    latest: datetime | None = None
    for n in notes:
        haystack = f"{n.title} {n.content}"
        if not text_matches_any(haystack, keywords):
            continue
        if n.created_at is None:
            continue
        if latest is None or n.created_at > latest:
            latest = n.created_at
    return latest


def days_since(dt: datetime | None, now: datetime) -> int | None:
    if dt is None:
        return None
    return (now - dt).days


def classify(days: int | None, threshold: int) -> str:
    if days is None:
        return "never"
    return "ok" if days <= threshold else "overdue"


def build_rows(companies: list[CompanyRecord], board_days: int, kpi_days: int) -> list[CadenceRow]:
    now = datetime.now(timezone.utc)
    rows: list[CadenceRow] = []
    for c in companies:
        board_last = most_recent_match(c.notes, BOARD_KEYWORDS)
        kpi_last = most_recent_match(c.notes, KPI_KEYWORDS)
        b_days = days_since(board_last, now)
        k_days = days_since(kpi_last, now)
        rows.append(
            CadenceRow(
                name=c.name,
                board_last=board_last,
                board_days=b_days,
                board_status=classify(b_days, board_days),
                kpi_last=kpi_last,
                kpi_days=k_days,
                kpi_status=classify(k_days, kpi_days),
            )
        )
    return rows


def percent_score(pct: float, thresholds: list[tuple[float, int]]) -> int:
    for threshold, points in thresholds:
        if pct >= threshold:
            return points
    return 0


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


@dataclass
class DimensionScore:
    label: str
    points: int
    max_points: int
    ok_count: int
    overdue_count: int
    never_count: int
    total: int
    threshold_days: int

    @property
    def pct_ok(self) -> float:
        return (self.ok_count / self.total * 100) if self.total else 0.0

    @property
    def pct_never(self) -> float:
        return (self.never_count / self.total * 100) if self.total else 0.0


def score_dimension(rows: list[CadenceRow], attr: str, threshold_days: int, max_points: int, label: str) -> DimensionScore:
    status_field = f"{attr}_status"
    statuses = [getattr(r, status_field) for r in rows]
    total = len(statuses)
    ok = sum(1 for s in statuses if s == "ok")
    never = sum(1 for s in statuses if s == "never")
    overdue = total - ok  # overdue includes "never" -- no evidence is not "on cadence"
    pct_ok = (ok / total * 100) if total else 0
    points = percent_score(pct_ok, [(90, max_points), (75, round(max_points * 0.7)), (50, round(max_points * 0.4)), (25, round(max_points * 0.16))])
    return DimensionScore(
        label=label,
        points=points,
        max_points=max_points,
        ok_count=ok,
        overdue_count=overdue,
        never_count=never,
        total=total,
        threshold_days=threshold_days,
    )


# --- Rendering ------------------------------------------------------------


def _fmt_days(days: int | None) -> str:
    if days is None:
        return "never found"
    return f"{days}d ago"


def render_markdown(meta: dict, rows: list[CadenceRow], board: DimensionScore, kpi: DimensionScore) -> str:
    out: list[str] = []
    out.append(f"# Attio VC Portfolio Health: {meta['fund_name']}")
    out.append("")
    out.append(f"**Workspace:** `{meta['workspace_slug']}` &nbsp;·&nbsp; **Source:** {meta['source_label']} &nbsp;·&nbsp; **Run:** {meta['run_ts']}")
    out.append("")
    out.append(meta["detection_note"])
    out.append(
        f"**Portfolio companies scanned:** {len(rows)} ({meta['scope_note']}) &nbsp;·&nbsp; "
        f"**Board threshold:** {meta['board_days']} days &nbsp;·&nbsp; **KPI threshold:** {meta['kpi_days']} days"
    )
    out.append("")
    out.append(
        "Post-investment tracking hygiene: how current is board-meeting and KPI-reporting note "
        "activity on companies already invested in, derived entirely from linked Notes' title/"
        "content. This is not a pipeline hygiene score -- see the sibling skill "
        "`attio-vc-ic-pipeline-prep` for that."
    )
    out.append("")
    out.append("---")
    out.append("")

    total_points = board.points + kpi.points
    total_max = board.max_points + kpi.max_points
    total_score = round(total_points / total_max * 100) if total_max else 0
    out.append(f"## Portfolio Health: **{total_score}/100 ({grade_letter(total_score)})**")
    out.append("")
    out.append(f"`{bar(total_score, 100, width=40)}`")
    out.append("")

    if not rows:
        out.append(
            "_No portfolio companies detected -- see the detection note above. Nothing to score._"
        )
        out.append("")
    else:
        for dim in (board, kpi):
            out.append(f"### {dim.label}: {dim.points}/{dim.max_points}")
            out.append(f"`{bar(dim.points, dim.max_points)}`")
            out.append("")
            out.append(
                f"- {dim.ok_count}/{dim.total} companies ({dim.pct_ok:.0f}%) have a matching note "
                f"within {dim.threshold_days} days: {dim.points}/{dim.max_points}"
            )
            if dim.never_count:
                out.append(
                    f"- {dim.never_count}/{dim.total} companies ({dim.pct_never:.0f}%) have **no note "
                    f"ever** matching these keywords -- this may mean the cadence isn't happening, or "
                    f"that it's happening but never logged with a recognizable title/keyword. Both are "
                    f"real findings about this workspace's Attio hygiene, not a bug in this tool."
                )
            out.append("")

        out.append("### Where to focus")
        deficits = sorted(
            [(d.max_points - d.points, d.label) for d in (board, kpi) if d.max_points - d.points >= 3],
            reverse=True,
        )
        if deficits:
            for i, (deficit, label) in enumerate(deficits, start=1):
                out.append(f"{i}. **{label}** ({deficit} points available)")
        else:
            out.append("- Cadence hygiene is in good shape on both dimensions checked. Maintain current practice.")
        out.append("")

        out.append("---")
        out.append("")
        out.append(f"## Cadence detail ({len(rows)} companies)")
        out.append("")
        out.append("| Company | Last board note | Last KPI note |")
        out.append("|---|---|---|")
        # Worst-first: sort by whichever cadence is more overdue (never > overdue > ok),
        # then by days descending within a status, so the companies needing attention
        # surface at the top of a possibly-truncated table.
        status_rank = {"never": 0, "overdue": 1, "ok": 2}

        def sort_key(r: CadenceRow):
            worst = min(status_rank[r.board_status], status_rank[r.kpi_status])
            days_key = -(max(r.board_days or 10**9, r.kpi_days or 10**9))
            return (worst, days_key)

        sorted_rows = sorted(rows, key=sort_key)
        shown = sorted_rows[:MAX_TABLE_ROWS]
        for r in shown:
            board_cell = f"{_fmt_days(r.board_days)} ({r.board_status})"
            kpi_cell = f"{_fmt_days(r.kpi_days)} ({r.kpi_status})"
            out.append(f"| {r.name} | {board_cell} | {kpi_cell} |")
        remainder = len(sorted_rows) - len(shown)
        if remainder > 0:
            out.append(f"| _(+{remainder} more, sorted best-cadence-first)_ | | |")
        out.append("")

    out.append("---")
    out.append("")
    out.append(
        "Generated by [5050-vc-skills](https://github.com/NachoLafuente/5050-vc-skills). "
        "Open source from [5050Growth](https://5050growth.com)."
    )
    return "\n".join(out)


def render_json(meta: dict, rows: list[CadenceRow], board: DimensionScore, kpi: DimensionScore) -> dict:
    total_points = board.points + kpi.points
    total_max = board.max_points + kpi.max_points
    total_score = round(total_points / total_max * 100) if total_max else 0
    return {
        "workspace": {"slug": meta["workspace_slug"], "name": meta["fund_name"]},
        "source": meta["source_label"],
        "detection": meta["detection_note"],
        "scope": meta["scope_note"],
        "thresholds": {"board_days": meta["board_days"], "kpi_days": meta["kpi_days"]},
        "portfolio_health": {
            "grade": grade_letter(total_score),
            "score": total_score,
            "max_score": 100,
            "dimensions": [
                {
                    "name": dim.label,
                    "points": dim.points,
                    "max_points": dim.max_points,
                    "ok_count": dim.ok_count,
                    "overdue_count": dim.overdue_count,
                    "never_count": dim.never_count,
                    "total": dim.total,
                    "threshold_days": dim.threshold_days,
                }
                for dim in (board, kpi)
            ],
        },
        "companies": [
            {
                "name": r.name,
                "board_last_note": r.board_last.isoformat() if r.board_last else None,
                "board_days_since": r.board_days,
                "board_status": r.board_status,
                "kpi_last_note": r.kpi_last.isoformat() if r.kpi_last else None,
                "kpi_days_since": r.kpi_days,
                "kpi_status": r.kpi_status,
            }
            for r in rows
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

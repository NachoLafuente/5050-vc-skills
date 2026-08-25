"""
Hygiene-grade half of attio-vc-ic-pipeline-prep: the 0-100 dealflow-hygiene
score across four dimensions (source-of-intro coverage, thesis/classification
coverage, stage-gate hygiene, interaction coverage).

This is the scoring logic that used to be the whole of attio-vc-pipeline-audit
-- unchanged here except that stage-attribute detection, closed-status titles,
and Notes are now looked up once in ic_pipeline_prep.py's main() and passed
in, instead of this module fetching its own copy (see _common.py's module
docstring for why). The actual detection keywords, percent-to-points
thresholds, and section text are identical to the original script.

Read-only: this module makes no API calls itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from _common import (
    active_stage_records,
    bar,
    find_attributes,
    grade_letter,
    is_filled,
    percent_score,
    record_last_touched,
)

# Attribute-detection keywords: matched as whole words against attribute
# title/api_slug (see find_attributes in _common.py). Whole-word matching
# matters here -- a naive substring check on "tag" would also match "stage"
# (s-TAG-e).
SOURCE_KEYWORDS = [
    "source of intro",
    "how sourced",
    "referred by",
    "referral",
    "sourced by",
    "intro source",
    "lead source",
    "source",
]
THESIS_KEYWORDS = [
    "thesis",
    "sector",
    "vertical",
    "industry",
    "classification",
    "category",
    "focus area",
    "sub sector",
    "investment stage",
    "company stage",
    "round stage",
    "stage of company",
    "market segment",
    "tag",
]


@dataclass
class Section:
    name: str
    score: int
    max_score: int
    applicable: bool = True
    findings: list[str] = field(default_factory=list)


def score_field_coverage(
    name: str, keywords: list[str], attrs: list[dict], records: list[dict], not_found_hint: str
) -> Section:
    section = Section(name=name, score=0, max_score=25)
    matches = find_attributes(attrs, keywords)
    if not matches:
        section.applicable = False
        section.findings.append(f"No {not_found_hint} field detected on this object -- skipped.")
        return section

    labels = ", ".join(f"`{a.get('title') or a.get('api_slug')}`" for a in matches[:4])
    more = f" (+{len(matches) - 4} more)" if len(matches) > 4 else ""
    section.findings.append(f"Matched field(s): {labels}{more}")

    if not records:
        section.findings.append(f"No records in sample to check: 0/{section.max_score}")
        return section

    match_slugs = [a.get("api_slug") for a in matches if a.get("api_slug")]
    filled = 0
    for r in records:
        values = r.get("values") or {}
        if any(is_filled(values.get(slug)) for slug in match_slugs):
            filled += 1

    pct = filled / len(records) * 100
    pts = percent_score(pct, [(85, 25), (65, 18), (40, 10), (15, 4)])
    section.score = pts
    section.findings.append(
        f"{pct:.0f}% of deals have this populated ({filled}/{len(records)}): {pts}/{section.max_score}"
    )
    return section


def score_source_of_intro(attrs: list[dict], records: list[dict]) -> Section:
    return score_field_coverage(
        "Source-of-intro coverage", SOURCE_KEYWORDS, attrs, records, "source-of-intro / referral"
    )


def score_thesis_classification(attrs: list[dict], records: list[dict]) -> Section:
    return score_field_coverage(
        "Thesis/classification coverage",
        THESIS_KEYWORDS,
        attrs,
        records,
        "thesis, sector, or stage-of-company classification",
    )


def score_stage_gate_hygiene(
    records: list[dict],
    stage_attr: dict | None,
    closed_titles: set[str] | None,
    stage_error: str | None,
    stale_days: int,
) -> Section:
    """Same scoring as the original attio-vc-pipeline-audit dimension. Takes
    the already-detected stage attribute and already-fetched closed-status
    titles as arguments (computed once in ic_pipeline_prep.py's main() and
    shared with the movement half) instead of calling fetch_statuses itself.
    """
    section = Section(name="Stage-gate hygiene", score=0, max_score=25)
    if stage_attr is None:
        section.applicable = False
        section.findings.append(
            "No clear pipeline-stage (status-type) attribute detected on this object -- skipped. "
            "This workspace may model stage differently, or have multiple status fields with "
            "ambiguous names."
        )
        return section

    stage_slug = stage_attr.get("api_slug")
    stage_label = stage_attr.get("title") or stage_slug

    if closed_titles is None:
        section.applicable = False
        section.findings.append(stage_error or f"Could not read status options for `{stage_label}` -- skipped.")
        return section

    closed_note = ", ".join(sorted(closed_titles)) if closed_titles else "none detected (all statuses treated as active)"
    section.findings.append(f"Stage attribute: `{stage_label}`. Treated as closed/inactive: {closed_note}")

    active_records = active_stage_records(records, stage_slug, closed_titles)

    if not active_records:
        section.score = section.max_score
        section.findings.append(
            f"No records currently sitting in an active (non-closed) `{stage_label}`: "
            f"{section.max_score}/{section.max_score}"
        )
        return section

    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
    stale = 0
    for r in active_records:
        touched = record_last_touched(r)
        if touched is None or touched < cutoff:
            stale += 1

    pct_stale = stale / len(active_records) * 100
    pct_fresh = 100 - pct_stale
    pts = percent_score(pct_fresh, [(90, 25), (75, 18), (50, 10), (25, 4)])
    section.score = pts
    section.findings.append(
        f"{stale}/{len(active_records)} active-stage deals ({pct_stale:.0f}%) not updated in "
        f"{stale_days}+ days: {pts}/{section.max_score}"
    )
    return section


def score_interaction_coverage(
    records: list[dict], all_noted_ids: set[str] | None, notes_error: str | None
) -> Section:
    """Same scoring as the original attio-vc-pipeline-audit dimension. Takes
    the set of every record id with at least one Note (any date, already
    fetched once in ic_pipeline_prep.py's main() and shared with the movement
    half's window-filtered version of the same Notes) instead of paginating
    /notes itself.
    """
    section = Section(name="Interaction coverage", score=0, max_score=25)
    if not records:
        section.applicable = False
        section.findings.append("No records in sample to check -- skipped.")
        return section

    if all_noted_ids is None:
        section.applicable = False
        section.findings.append(notes_error or "Could not read Notes -- token may lack note read scope. Skipped.")
        return section

    record_ids = [(r.get("id") or {}).get("record_id") for r in records]
    record_ids = [rid for rid in record_ids if rid]
    with_notes = sum(1 for rid in record_ids if rid in all_noted_ids)
    total = len(record_ids)
    pct_with_notes = with_notes / total * 100 if total else 0
    pts = percent_score(pct_with_notes, [(80, 25), (60, 18), (35, 10), (15, 4)])
    section.score = pts
    zero = total - with_notes
    section.findings.append(
        f"{zero}/{total} deals ({100 - pct_with_notes:.0f}%) have zero linked Notes: {pts}/{section.max_score}"
    )
    section.findings.append(
        "Measures logged Notes only. Attio's synced email/calendar interaction attributes "
        "(last_interaction, etc.) live on People and Companies, not on custom deal-type objects, "
        "so they cannot be read from a deal record directly."
    )
    return section


# --- Rendering (Part 1 of the combined report; no outer H1/header -- "
# ic_pipeline_prep.py supplies the shared workspace header) -------------------


def render_hygiene(sections: list[Section], total: int) -> list[str]:
    out: list[str] = []
    applicable = [s for s in sections if s.applicable]
    skipped = [s for s in sections if not s.applicable]

    out.append(f"## Part 1 -- Pipeline Hygiene Grade: **{total}/100 ({grade_letter(total)})**")
    out.append("")
    out.append(f"`{bar(total, 100, width=40)}`")
    out.append("")
    if skipped:
        skipped_names = ", ".join(s.name for s in skipped)
        out.append(
            f"_Scored on {len(applicable)}/4 dimensions. Skipped: {skipped_names} (see notes below). "
            "Grade is rescaled across applicable dimensions._"
        )
        out.append("")

    for s in sections:
        tag = " -- not applicable" if not s.applicable else ""
        out.append(f"### {s.name}: {s.score}/{s.max_score}{tag}")
        if s.applicable:
            out.append(f"`{bar(s.score, s.max_score)}`")
        out.append("")
        for f in s.findings:
            out.append(f"- {f}")
        out.append("")

    fix_priorities = []
    for s in applicable:
        deficit = s.max_score - s.score
        if deficit >= 5:
            fix_priorities.append((deficit, s.name))
    fix_priorities.sort(reverse=True)
    out.append("### Where to focus")
    if fix_priorities:
        for i, (deficit, nm) in enumerate(fix_priorities[:3], start=1):
            out.append(f"{i}. **{nm}** ({deficit} points available)")
    else:
        out.append("- Pipeline hygiene is in good shape on the dimensions checked. Maintain current practice.")
    out.append("")
    return out


def hygiene_to_dict(sections: list[Section], total: int) -> dict:
    applicable = [s for s in sections if s.applicable]
    return {
        "grade": grade_letter(total),
        "score": total,
        "max_score": 100,
        "dimensions_scored": len(applicable),
        "dimensions_total": len(sections),
        "sections": [
            {
                "name": s.name,
                "score": s.score,
                "max_score": s.max_score,
                "applicable": s.applicable,
                "findings": s.findings,
            }
            for s in sections
        ],
    }

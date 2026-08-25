---
name: attio-vc-ic-pipeline-prep
description: Prep the pipeline-status open of a VC/PE fund's IC meeting from their own Attio deal pipeline -- a 0-100 dealflow-hygiene grade (source-of-intro coverage, thesis/classification coverage, stage-gate hygiene, interaction coverage) followed by a written digest of what moved since the last check-in (new deals, deals that advanced a stage, deals gone stale, DD/activity delta from logged Notes). Use when the user asks to "prep for IC", "get the pipeline ready for Monday IC", "audit our deal pipeline", "check our Attio dealflow hygiene", "grade our pipeline", "what moved in the pipeline this week", "which deals went stale", or pastes an Attio API key for a fund/investment workspace and wants a grade and/or a recap of recent activity. This is NOT a per-deal investment memo -- see the sibling skill attio-vc-ic-memo-prep for that. Auto-detects the deal/investment/opportunity object; accepts --object override. Read-only, samples up to 500 deal records and 500 notes by default. Output is one combined markdown report (or JSON with --json): hygiene grade section first, movement digest section second.
license: MIT
author: 5050Growth
---

# attio-vc-ic-pipeline-prep

Prep the pipeline-status open of a VC/PE fund's IC meeting from their own Attio deal pipeline.
Read-only, no writes.

This is the merge of two formerly-separate skills -- `attio-vc-pipeline-audit` (a 0-100 hygiene
grade) and `attio-vc-pipeline-movement` (a written movement digest). Real ICs open with exactly
this pair -- what's the pipeline's overall health, what moved since last time -- before individual
deal votes start. This skill renders both in one report instead of two.

**This is the pipeline-status open of an IC meeting. It is NOT a per-deal investment memo** -- it
does not evaluate any individual deal, and does not draft a thesis, market analysis, or risk
assessment for a company. For that, see the sibling skill
[attio-vc-ic-memo-prep](../attio-vc-ic-memo-prep/), which assembles a per-deal memo skeleton from
one record's fields and notes.

This is also not a generic Attio audit (see [attio-audit](../attio-audit/) in the sibling
[attio-toolkit](https://github.com/NachoLafuente/attio-toolkit) repo for that).

## When to use this skill

Run before a Monday IC / pipeline review, or any time a fund wants: (a) a quick health check of
how well their Attio pipeline is actually being worked, and (b) a recap of what happened since the
last check-in -- without opening Attio and scrolling every view by hand. Produces one grade, one
fix list, and one movement recap in a single read.

Do NOT use this skill if the user wants:
- A memo, IC deck, or written investment analysis for one specific deal (that's a drafted
  deliverable for `attio-vc-ic-memo-prep`, the sibling skill in this repo)
- A general Attio workspace audit not specific to the deal pipeline (use `attio-audit` instead)
- Deal scoring/evaluation from a pitch deck or public data (this reads existing CRM records only,
  it does not fetch or score anything outside the workspace)
- This same report delivered automatically on a schedule (Slack/email, tuned to the fund's exact
  stage names, zero maintenance) -- that's a paid engagement, see
  [5050Growth](https://5050growth.com). This script is the one-shot version: run it by hand, read
  it once.

## Inputs

The skill needs an Attio API token. Resolution order:
1. `--token <value>` flag
2. `ATTIO_API_KEY` env var
3. `ATTIO_OAUTH2` env var

If none are set, prompt the user for the token before running.

Optional `--object <slug>` to point at the deal object explicitly. Without it, the script
auto-detects by matching `api_slug` / `singular_noun` / `plural_noun` against deal/investment/
opportunity/pipeline/portfolio-company naming, with the standard Attio `deals` object always
winning outright. If nothing matches, or two objects tie for the top score, the script exits and
asks for `--object` rather than guessing. One detection pass covers both halves of the report.

## Before running: ask which scope

Before invoking the script, ask the user:

> "500-record / 500-note sample is enough for a representative report and runs in well under a
> minute. Want me to do all records and notes instead (slower, exact counts)?"

Default to the sample unless they ask for the full scan.

## How to run

Sample mode (default: 30-day stale threshold, 14-day movement window):

```bash
ATTIO_API_KEY=<token> python skills/attio-vc-ic-pipeline-prep/ic_pipeline_prep.py
```

Explicit object (when auto-detection is ambiguous or wrong):

```bash
ATTIO_API_KEY=<token> python skills/attio-vc-ic-pipeline-prep/ic_pipeline_prep.py --object investments
```

Custom staleness window for the hygiene grade (default 30 days):

```bash
ATTIO_API_KEY=<token> python skills/attio-vc-ic-pipeline-prep/ic_pipeline_prep.py --stale-days 45
```

Different lookback window for the movement digest (default 14 days):

```bash
ATTIO_API_KEY=<token> python skills/attio-vc-ic-pipeline-prep/ic_pipeline_prep.py --days 7
```

Full scan (paginates every record and every note):

```bash
ATTIO_API_KEY=<token> python skills/attio-vc-ic-pipeline-prep/ic_pipeline_prep.py --full
```

JSON output (works with any of the above):

```bash
ATTIO_API_KEY=<token> python skills/attio-vc-ic-pipeline-prep/ic_pipeline_prep.py --json
```

Flags can be combined, e.g. `--object investments --stale-days 45 --days 7 --full`.

## What gets checked -- Part 1: Pipeline Hygiene Grade

Each dimension is worth 25 points -- deliberately equal weight, since which one matters most
varies fund to fund (a pre-seed fund cares more about source coverage; a growth fund cares more
about stage-gate hygiene on a smaller, longer-cycle pipeline).

| Dimension | Max | What it measures |
|-----------|-----|------------------|
| Source-of-intro coverage | 25 | % of deals with a populated source-of-intro / referral / "how sourced" field |
| Thesis/classification coverage | 25 | % of deals with a populated sector, thesis-tag, or stage-of-company field |
| Stage-gate hygiene | 25 | % of deals in an active (non-closed) pipeline stage that HAVE been touched in the last N days (default 30, `--stale-days`) |
| Interaction coverage | 25 | % of deals with at least one linked Note (any date) |

Total: 0-100. Letter grade: A (90+), B (80+), C (70+), D (60+), F (<60).

Attribute detection is keyword-based (whole-word matching against attribute title/api_slug), not
hardcoded to any fund's schema. A dimension is skipped -- not scored zero -- when the relevant
attribute genuinely doesn't exist in the workspace, and the grade is rescaled across whatever
dimensions did apply. The report always says how many of the 4 dimensions were scored.

### How "stale" is computed

Attio does not expose a record-level `updated_at`. Every attribute value on a record is a
historical array (`active_from` / `active_until`); this skill takes the max `active_from` across
every attribute on a record as a proxy for "last time anything on this record changed," falling
back to `created_at` if no value history is readable. "Active stage" is whatever the object's
status-type pipeline attribute says, with closed/passed/won/lost-style titles excluded by keyword
match against the actual status options in the workspace (not a fixed list).

### How interaction coverage is computed

Attio's synced email/calendar interaction attributes (`last_interaction`, etc.) only exist on
People and Companies, never on custom or standard deal-type objects. So this dimension checks
linked Notes instead: whether a deal record's ID shows up as any Note's `parent_record_id`,
regardless of when that note was created. This is a proxy for "has anyone ever logged work on this
deal," not full activity history.

## What gets reported -- Part 2: Pipeline Movement (last N days)

Four buckets, each scoped to the `--days` lookback window (default 14):

| Bucket | What it shows |
|--------|---------------|
| New deals | Records created inside the window. Name + created date, newest first. |
| Advanced a stage | Deals whose pipeline stage changed inside the window. From-stage → to-stage where derivable. |
| Gone stale | Active-stage deals with no attribute change *and* no logged Note inside the window. |
| DD / activity delta | Total Notes logged in the window, plus which active deals got zero DD activity. |

### How "new" is computed

Straight `created_at` inside `[now - days, now]`.

### How "advanced a stage" is computed

Reuses the same stage-attribute detection as Part 1. A deal counts as "advanced" only if its stage
attribute has 2+ historical value entries (proof an actual change happened) and the
currently-active entry's `active_from` falls inside the window. A record with a single,
never-changed stage entry created inside the window is a new deal, not an advance -- the two
buckets don't overlap on that account.

### How "gone stale" is computed

Restricted to active-stage deals (same closed/active classification as Part 1). A deal is stale if
**both**: its last-touched timestamp (max `active_from` across every attribute) is older than the
window, **and** it has zero Notes created inside the window. Part 1's stage-gate dimension only
checks the first condition against `--stale-days`; this bucket adds the second condition against
`--days`, because a deal can get worked -- a call logged, a DD note added -- without any field on
the record itself changing.

### How DD/activity delta is computed

Every Note in the scanned sample whose `created_at` falls inside the `--days` window counts toward
the total. "Zero DD activity" lists active-stage deals with no such note, independent of whether
their other attributes changed (a looser condition than "gone stale" -- every stale deal has zero
DD activity, but not every deal with zero DD activity is stale, since its stage attribute might
have moved with no note logged).

## Output structure

One combined markdown report:
- Shared header: workspace name + slug + run timestamp, detected object (or explicit override),
  scan scope, stale threshold, movement window
- One-line framing that this is the pipeline-status open, not a per-deal memo
- **Part 1 -- Pipeline Hygiene Grade**: big total grade (rescaling note if any dimension was
  skipped), per-dimension breakdown, "Where to focus" (top 3 applicable dimensions by
  point-recovery potential)
- **Part 2 -- Pipeline Movement**: one-sentence summary, one section per bucket (record lists
  capped at 20 lines with a "+N more" tail), DD/activity delta section
- Footer credit

`--json` produces the same information as a single object with top-level `hygiene` and `movement`
keys instead of two separate JSON documents.

## Limitations

- Default mode samples 500 records and up to 500 notes. Both the grade and the digest are
  representative estimates over that sample, not exhaustive scans. Use `--full` for exact numbers.
- Object and stage-attribute auto-detection are name-based. A workspace with an oddly-named deal
  object (or more than one object that plausibly looks like a deal pipeline, or multiple
  ambiguously-named status fields) needs `--object`.
- Thesis/classification and source-of-intro detection match on attribute naming conventions. A
  workspace that encodes sourcing or thesis purely in free-text Notes rather than a structured
  field will show as 0% covered in Part 1 even if the information exists -- that's a real gap this
  tool is meant to surface, but it's worth knowing the failure mode.
- Notes are read in whatever order Attio's `/notes` endpoint returns them in, not guaranteed to
  correlate with recency. In sample mode this can affect both Part 1's interaction-coverage figure
  and Part 2's note-window count; `--full` paginates every note and removes this risk.
- "Advanced a stage" needs a readable *prior* stage-value entry to show a from → to transition. A
  record with corrupted or unreadable value history for its stage attribute falls back to "moved
  stage as of \<date\>" with no from-stage shown.
- Part 2 is a recap, not a diagnosis -- it does not explain *why* deals went stale or recommend
  process changes. Part 1 is a hygiene score, not an investment-decision tool. Neither evaluates
  deal quality, IRR, or anything about the investment itself.

## Safe to run on production

This skill makes only GET and POST-query calls (`/objects/{slug}/records/query`,
`/notes?parent_object=...`, `/objects/{slug}/attributes/{slug}/statuses`). It never writes,
deletes, or modifies anything. Records, stage statuses, and Notes are each fetched exactly once per
run and shared between the hygiene grade and the movement digest, so running this merged skill
makes fewer API calls than running the two predecessor scripts back to back would have. Safe to
run during business hours on a live workspace.

Tokens are read from `--token`, `ATTIO_API_KEY`, or `ATTIO_OAUTH2` -- never logged, never written
to disk, never sent anywhere but `https://api.attio.com/v2/`.

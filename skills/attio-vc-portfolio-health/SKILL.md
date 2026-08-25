---
name: attio-vc-portfolio-health
description: Post-investment tracking hygiene for a VC/PE fund's own portfolio (companies already invested in, not the pipeline) -- board-meeting cadence and KPI-reporting cadence, derived from linked Notes' title/content, scored against configurable day thresholds (default 45 for board, 30 for KPI). Use when the user asks to "check our portfolio hygiene", "are we tracking board meetings", "check KPI reporting cadence", "audit portfolio company tracking", "which portfolio companies are overdue on board updates", or pastes an Attio or Affinity API key for a fund/investment workspace and wants a portfolio-side (not pipeline-side) tracking check. This is NOT the pipeline hygiene grade -- see the sibling skill attio-vc-ic-pipeline-prep for that (which is Attio-only). Supports both Attio and Affinity via --source (auto-detected if only one token is set). Detects the portfolio company set automatically: a distinct "Portfolio"/"holding" object/list if one exists, otherwise the deal/investment object/list filtered to invested/closed-won-style records. Read-only, samples by default (Attio 500 records, Affinity 75 entries), --full for exact counts. Output is markdown (or JSON with --json): a 0-100 cadence grade (two 50-point dimensions) plus a per-company detail table.
license: MIT
author: 5050Growth
---

# attio-vc-portfolio-health

Post-investment tracking hygiene for the **portfolio side** of a VC/PE fund's CRM -- companies
already invested in, not the pipeline. Read-only, no writes. Supports Attio and Affinity.

**This checks the portfolio, not the pipeline.** For dealflow hygiene (source-of-intro coverage,
thesis tagging, stage-gate hygiene, interaction coverage) and a movement digest on deals still being
evaluated, see the sibling skill [attio-vc-ic-pipeline-prep](../attio-vc-ic-pipeline-prep/) (Attio
only). For a per-deal IC memo skeleton, see
[attio-vc-ic-memo-prep](../attio-vc-ic-memo-prep/) (Attio only). For co-investor/syndicate
relationship density, see [attio-vc-coinvestor-map](../attio-vc-coinvestor-map/) (Attio or
Affinity, like this skill).

## When to use this skill

Run when a fund wants to know whether its own post-investment tracking discipline is actually
happening: are board meetings getting logged, is KPI/investor reporting cadence being kept up,
across the companies it has already funded. This is a hygiene check on the fund's own CRM
discipline, not a portfolio-company performance review.

Do NOT use this skill if the user wants:
- Dealflow hygiene or a movement digest for deals still in the pipeline (use
  `attio-vc-ic-pipeline-prep` instead)
- A per-deal IC memo skeleton (use `attio-vc-ic-memo-prep` instead)
- Co-investor/syndicate coverage (use `attio-vc-coinvestor-map` instead)
- Actual KPI *values* (revenue, burn, runway) pulled and analyzed -- this tool only checks whether
  a KPI-reporting-shaped note was logged recently, it does not read or evaluate the numbers inside
  one

## Inputs

Two supported sources, resolved via `--source {attio,affinity}`:

- **Attio**: token via `--token`, `ATTIO_API_KEY`, or `ATTIO_OAUTH2`.
- **Affinity**: key via `--affinity-token` or `AFFINITY_API_KEY`. This is a **generic** env var
  name mirroring `ATTIO_API_KEY` -- never a client-scoped variable name. If you have a
  fund-specific Affinity key stashed under some other env var name, export it as `AFFINITY_API_KEY`
  before running this, don't edit the script to look for it.

If `--source` isn't given, it's inferred: whichever of `ATTIO_API_KEY`/`AFFINITY_API_KEY` (or
their `--token`/`--affinity-token` equivalents) is actually set wins. If both or neither are set,
the script exits and asks for `--source` explicitly rather than guessing which CRM you meant.

Optional `--object <slug>` (Attio) or `--list <id-or-name>` (Affinity) to point at the portfolio
object/list explicitly, overriding auto-detection.

## Before running: ask which scope, and check the source

Before invoking the script:

1. Confirm the source. If the user hasn't said Attio or Affinity, and both env vars happen to be
   set, ask which workspace they mean.
2. On Attio: same as the sibling skills -- default sample (500 records) is representative and
   fast; offer `--full` for exact counts.
3. **On Affinity: this is the important one.** Affinity's API has a hard monthly call budget, and
   this skill's cost depends entirely on which detection path it takes (see "Two very different
   cost profiles" below). Always let the script print the `/rate-limit` budget line before deciding
   whether `--full` is worth it. If the workspace turns out to need the stage-filtered fallback
   path (no distinct Portfolio list), `--full` requires an explicit `--yes-i-know` confirmation --
   don't pass that flag on the user's behalf without them understanding why it's gated.

## How to run

Attio, sample mode (default 45-day board threshold, 30-day KPI threshold):

```bash
ATTIO_API_KEY=<token> python skills/attio-vc-portfolio-health/portfolio_health.py
```

Affinity:

```bash
AFFINITY_API_KEY=<key> python skills/attio-vc-portfolio-health/portfolio_health.py --source affinity
```

Explicit object/list (when auto-detection is ambiguous or wrong):

```bash
python skills/attio-vc-portfolio-health/portfolio_health.py --object portfolio_companies
python skills/attio-vc-portfolio-health/portfolio_health.py --source affinity --list "Portfolio"
```

Custom thresholds:

```bash
python skills/attio-vc-portfolio-health/portfolio_health.py --board-days 60 --kpi-days 45
```

JSON output:

```bash
python skills/attio-vc-portfolio-health/portfolio_health.py --json
```

Full scan on Attio (cheap, no gate):

```bash
python skills/attio-vc-portfolio-health/portfolio_health.py --full
```

Full scan on Affinity when the stage-filtered fallback path is in use (real per-entity spend, gated):

```bash
python skills/attio-vc-portfolio-health/portfolio_health.py --source affinity --full --yes-i-know
```

## How the portfolio set is detected

Most VC Attio/Affinity workspaces do **not** have a separate "portfolio" object or list -- the same
deal/investment object/list used for the whole pipeline usually just has a closed-won/invested-style
status. This skill checks for a dedicated one first, and falls back if it doesn't exist:

1. **Prefer a distinct object/list** whose name keyword-matches `portfolio` or `holding` (and isn't
   the same object already matched as the general deal object). If found, every record/entry in it
   counts as a portfolio company -- no status filtering, since membership already implies invested.
2. **Otherwise, fall back** to the deal/investment/opportunity object (Attio) or list (Affinity),
   filtered to records/entries whose current stage/status reads as invested/closed-won/portfolio --
   matched by keyword against status titles, explicitly *excluding* anything that reads as
   lost/passed/declined/dead/rejected/withdrawn/abandoned even if it also contains a word like
   "closed" (so "Closed Lost" is never counted as invested just because it's inactive).

Both paths are keyword-based, not hardcoded to any one fund's schema -- see Limitations for the
failure mode.

### Two very different cost profiles on Affinity

- **Distinct portfolio list found** (the common real-world case -- e.g. a list literally named
  "Portfolio"): cheap. List-entries and Notes are both bulk-paginated calls, nothing per-entity.
  `--full` here is safe and never gated.
- **No distinct list, stage-filtered fallback used**: Affinity has no bulk field-value endpoint, so
  telling "invested" apart from "still active"/"passed" costs one `/field-values` call per sampled
  entry. This path uses the same small-sample-by-default-unless-`--full`-with-`--yes-i-know`
  guardrail as the sibling skill `attio-vc-coinvestor-map`. The report's scope line always says
  which path ran.

## Board-meeting and KPI-reporting cadence

For each portfolio company, every linked Note (Attio) or every note in the account grouped locally
by organization/person/opportunity id (Affinity -- see "Affinity object-model notes" below) is
scanned for two keyword sets in the note's title + whatever content text was readable:

| Cadence | Keywords checked |
|---|---|
| Board-meeting | `board meeting`, `board update`, `board deck`, `board minutes`, `board pack` |
| KPI-reporting | `kpi`, `metrics update`, `monthly update`, `investor update` |

The most recent matching note's date, per category per company, is the basis for "days since last
board/KPI note." A company with **zero** matching notes ever is "never," not "0 days overdue" --
that distinction matters and is called out separately in the report.

**This depends on notes actually containing recognizable keywords.** A fund that logs board notes
diligently but never writes the word "board" anywhere in the title or body will show as 0% covered
on that dimension. **That is a real finding about this workspace's note-taking hygiene, not a bug
in this tool.** Never assume the cadence is "probably happening anyway" -- report exactly what the
notes show, and let the fund confirm or correct it.

## Scoring

Two dimensions, 50 points each (Board-meeting cadence, KPI-reporting cadence) -- equal weight,
deliberately, since which one matters more varies fund to fund. Points scale with the % of
portfolio companies with a matching note inside the threshold (`--board-days` / `--kpi-days`,
default 45 / 30): 90%+ → full points, 75%+ → 70%, 50%+ → 40%, 25%+ → 16%, below → 0. Total 0-100
with a letter grade (A 90+, B 80+, C 70+, D 60+, F below), same letters as the sibling skill's
hygiene grade.

## Output structure

Markdown (or JSON with `--json`):
- Header: fund/workspace, source, run timestamp, detection note (which path was used and why),
  companies scanned, thresholds
- **Portfolio Health** total grade, per-dimension breakdown (points, % on-cadence, % never-found),
  "Where to focus"
- **Cadence detail** table, worst-first, capped at 20 rows with a "+N more" tail

## Limitations

- Detection (object/list, status/stage) is name-based on both platforms. A workspace with unusual
  naming for its portfolio object or its status options needs `--object`/`--list`.
- Cadence detection only reads whatever content text was already present in each platform's notes
  list response -- Attio's list response (checked for `content_plaintext`/`content_markdown`/etc.)
  and Affinity's (which already carries full note content inline). Neither backend makes an
  additional per-note GET to fetch a fuller body; scanning a whole portfolio's notes for keywords
  with a per-note fallback call would multiply calls exactly the way this skill's Affinity design is
  built to avoid.
- Sample mode caps records/entries (Attio 500, Affinity 75 by default) and notes (10 pages per
  platform: 500 for Attio, 5,000 for Affinity). `--full` paginates everything -- cheap on Attio and
  on Affinity's distinct-portfolio-list path, gated behind `--yes-i-know` on Affinity's
  stage-filtered fallback path.
- This is a hygiene/cadence check, not a KPI-quality or board-effectiveness review. It never reads
  or evaluates what's inside a matching note, only whether one exists and when.

## Affinity object-model notes

Affinity has no native "Notes linked to a Note-taking-cadence field" concept -- notes are their own
entity, filterable by `organization_id`/`person_id`/`opportunity_id`, but this skill fetches the
account's notes **unfiltered** (paginated, bulk, cheap) and groups them locally by each note's
`organization_ids`/`person_ids`/`opportunity_ids` against the detected portfolio entities' ids --
the same "fetch once, group locally" approach the Attio side already uses for its own Notes. This
keeps cadence-checking cheap regardless of portfolio size, unlike the co-investor lookup in the
sibling skill `attio-vc-coinvestor-map`, which genuinely needs one call per entity because the value
it needs lives in a field, not a note.

## Safe to run on production

Attio: only GET and POST-query calls (`/objects/{slug}/records/query`, `/objects/{slug}/
attributes/{slug}/statuses`, `/notes?parent_object=...`). Affinity: only GET calls (`/rate-limit`,
`/lists`, `/lists/{id}/list-entries`, `/fields`, `/notes`, and -- only on the stage-filtered
fallback path -- `/field-values`). Neither platform is ever written to, deleted from, or modified.

Tokens: Attio from `--token`/`ATTIO_API_KEY`/`ATTIO_OAUTH2`; Affinity from
`--affinity-token`/`AFFINITY_API_KEY` (generic name only, never a client-scoped variable). Never
logged, never written to disk, never sent anywhere but `https://api.attio.com/v2/` or
`https://api.affinity.co/` respectively.

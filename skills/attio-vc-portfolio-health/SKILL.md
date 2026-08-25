---
name: attio-vc-portfolio-health
description: Post-investment tracking hygiene for a VC/PE fund's own portfolio (companies already invested in, not the pipeline) -- board-meeting cadence and KPI-reporting cadence, derived from linked Notes' title/content, scored against configurable day thresholds (default 45 for board, 30 for KPI). Use when the user asks to "check our portfolio hygiene", "are we tracking board meetings", "check KPI reporting cadence", "audit portfolio company tracking", "which portfolio companies are overdue on board updates", or wants a portfolio-side (not pipeline-side) tracking check for a fund/investment Attio or Affinity workspace. This is NOT the pipeline hygiene grade -- see the sibling skill attio-vc-ic-pipeline-prep for that (which is Attio-only). Supports both Attio and Affinity via --source (auto-detected if only one token is set). On Attio, the default data source is the Attio MCP tools (mcp__attio-official__*) already connected in the session -- Claude gathers data via MCP tool calls, assembles a JSON bundle, and runs the script with --input; --token/ATTIO_API_KEY is the fallback. Affinity has no MCP equivalent in scope here and always uses --affinity-token/AFFINITY_API_KEY. Detects the portfolio company set automatically: a distinct "Portfolio"/"holding" object/list if one exists, otherwise the deal/investment object/list filtered to invested/closed-won-style records. Read-only on every path, samples by default (Attio 500 records or an MCP-page-bounded equivalent, Affinity 75 entries), --full for exact counts. Output is markdown (or JSON with --json): a 0-100 cadence grade (two 50-point dimensions) plus a per-company detail table.
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

Two supported sources. **Affinity has no MCP equivalent in scope here** -- it always uses
`--affinity-token`/`AFFINITY_API_KEY`. Attio has two paths:

- **Attio, default: MCP.** If `mcp__attio-official__*` tools are present in the current session's
  tool list, that's the data source for Attio -- no API key needed. Claude gathers data via MCP tool
  calls, assembles a JSON bundle, and runs the script with `--input <bundle-path>`. See "Gathering
  data via MCP (Attio only)" below.
- **Attio, fallback: API token.** `--token`, `ATTIO_API_KEY`, or `ATTIO_OAUTH2`, if the VC says they
  don't have Attio connected via MCP, or prefers an API key.
- **Affinity: API key.** `--affinity-token` or `AFFINITY_API_KEY`. This is a **generic** env var
  name mirroring `ATTIO_API_KEY` -- never a client-scoped variable name. If you have a
  fund-specific Affinity key stashed under some other env var name, export it as `AFFINITY_API_KEY`
  before running this, don't edit the script to look for it.

`--source` picks which CRM: pass `--input` for Attio-via-MCP (source is implied), or
`--source {attio,affinity}` for the token/key paths. If `--source` isn't given and no `--input` is
set, it's inferred from whichever of `ATTIO_API_KEY`/`AFFINITY_API_KEY` (or their
`--token`/`--affinity-token` equivalents) is actually set. If both or neither are set, the script
exits and asks for `--source` explicitly rather than guessing which CRM you meant.

Optional `--object <slug>` (Attio) or `--list <id-or-name>` (Affinity) to point at the portfolio
object/list explicitly, overriding auto-detection, on any path.

## Gathering data via MCP (Attio only)

Affinity is unaffected by this section -- it's always `--affinity-token`/`AFFINITY_API_KEY`, no MCP
path exists for it in this repo's scope.

This skill detects the portfolio set two ways (see "How the portfolio set is detected" below): a
distinct Portfolio/Holding object, or the general deal object filtered by invested-style status.
Under MCP, Claude makes that same judgment call before assembling the bundle -- the script's
`load_from_input()` doesn't re-derive which path applies, it infers it from what's *in* the bundle
(presence of a usable stage attribute plus `stage_statuses` triggers filtering; their absence means
"every record in the bundle already is a portfolio company").

### 1. Find the portfolio object (or the deal object, if no distinct one exists)

Call `list-lists` (optionally `query: "portfolio"` or `"holding"`) first -- if a list's parent object
type reads as a dedicated portfolio/holding object (not the same object as the general deal
pipeline), that's the distinct-object case: every record in it is a portfolio company, no status
filtering needed or possible.

If nothing distinct turns up, fall back to the same deal-object discovery the sibling skill
`attio-vc-ic-pipeline-prep` uses (try `list-attribute-definitions` with `object: "deals"` first, else
inspect `list-lists`' parent-object-type field for deal/investment/pipeline naming) -- that's the
stage-filtered case.

### 2. Distinct-object case: pull records and notes, done

`list-attribute-definitions` for `attributes`, `list-records` (paginated in 50-record MCP pages) for
`records`, and for each record's notes, `search-notes-by-metadata` with `parent_record_id` +
`parent_record_object` then `get-note-body` per note id -- **this needs one such call pair per
company**, not a windowed workaround, because cadence checking needs "most recent match ever," not
bounded by a lookback window (unlike the sibling pipeline-prep skill's movement digest, which can use
a time-window strategy because it only cares about recent activity). State plainly in the report if
this makes the MCP path noticeably more call-heavy than a workspace with few portfolio companies
would suggest -- it scales with portfolio size, one note-fetch round-trip per company, same shape as
the token path's own per-company completeness (Attio's REST `/notes` sweep is bulk-paginated and
cheap; the MCP equivalent isn't, since there's no object-wide notes scope to page through). Leave
`stage_statuses` out of the bundle entirely for this case -- its absence is what signals
"already-scoped, don't filter."

### 3. Stage-filtered case: pull records, stage statuses, and notes

Same as step 1 plus 4 in the sibling skill `attio-vc-ic-pipeline-prep`'s "Gathering data via MCP"
section: pull `attributes`, `records` (50-record MCP pages), and populate `stage_statuses` from the
distinct status titles observed on the fetched records' current stage values (no verified MCP
equivalent of the direct API's per-attribute status-options endpoint -- same caveat as the sibling
skill). Then, same per-company note-fetch as step 2 above, but only for records whose current stage
reads as invested/closed-won (classify client-side against `invested`, `portfolio`, `won`, `closed`,
excluding anything reading as `lost`/`passed`/`declin`/`dead`/`reject`/`withdraw`/`abandon`/`not
pursu` -- same keyword sets `classify_invested_statuses()` already uses) so MCP calls aren't spent on
pipeline-only deals this skill doesn't need. Note: unlike the token path's `_load_stage_filtered()`
(which pulls notes for every record in the object regardless of status, since Attio's `/notes` sweep
is one bulk call either way), the MCP path benefits from filtering to invested-status records
*before* the per-record note calls, since each one has a real cost here.

### 4. Assemble and run

```json
{
  "workspace_name": "<fund/workspace display name>",
  "workspace_slug": "<short human-provided identifier -- see the sibling pipeline-prep skill's 'Workspace identity under MCP' note>",
  "object_slug": "portfolio_companies",
  "object_label": "Portfolio Company",
  "attributes": [{"api_slug": "name", "title": "Name", "type": "text"}],
  "records": [
    {
      "id": {"record_id": "4f8a21c3-9e2b-4a11-8f3d-2c7b6a1e9d40"},
      "created_at": "2026-01-10T09:00:00.000Z",
      "values": {"name": [{"active_from": "2026-01-10T09:00:00.000Z", "active_until": null, "value": "Acme Robotics"}]}
    }
  ],
  "notes": [
    {
      "id": {"note_id": "9c1e2b3a-4f11-4a1b-9e2b-1a2b3c4d5e6f"},
      "parent_record_id": "4f8a21c3-9e2b-4a11-8f3d-2c7b6a1e9d40",
      "created_at": "2026-08-01T09:00:00.000Z",
      "title": "Q3 board meeting",
      "content_plaintext": "Full note text from get-note-body here."
    }
  ]
}
```

(This example omits `stage_statuses` -- the distinct-object case. Include it, populated per step 3,
for the stage-filtered case.) Same degraded-precision caveat as the sibling skills applies if MCP
returns flat current-value records instead of the historicized shape shown; impact here is limited
to whether `current_status_title()` reads the right value on the stage-filtered path.

Write the bundle to a temp file, then:

```bash
python skills/attio-vc-portfolio-health/portfolio_health.py --input /path/to/bundle.json
```

`--board-days`/`--kpi-days`/`--json` still work exactly as on the token path. `--source`, `--token`,
`--object`, `--full`, and `--detect-only` don't apply when `--input` is set (detection already
happened in steps 1-3 above).

## First run: confirm once, skip the guessing forever

The first time this skill runs against a workspace with no saved config, it guesses the portfolio
object/list, and -- if no distinct portfolio object/list exists -- which statuses count as
invested/closed-won, by keyword match. A human can confirm those answers once instead of the tool
re-guessing (and risking a misclassification, e.g. a status literally named "Closed - Not Pursued"
reading as invested purely because it contains "closed") on every single run.

**On Attio via MCP:** there's no separate `--detect-only` MCP mode -- steps 1 and 3 of "Gathering
data via MCP" above already are the detection pass (which object/list, and, on the stage-filtered
path, candidate invested-status titles derived from observed records). Do that detection work first,
ask the human the same short questions below, then write the config -- same file, same shape, before
pulling per-company notes and building the full bundle.

**On Attio via token, or on Affinity, for a workspace with no `.vc-skills-config/<workspace-slug>.json` file:**

1. Run `--detect-only` for the relevant source:
   ```bash
   ATTIO_API_KEY=<token> python skills/attio-vc-portfolio-health/portfolio_health.py --source attio --detect-only
   AFFINITY_API_KEY=<key> python skills/attio-vc-portfolio-health/portfolio_health.py --source affinity --detect-only
   ```
   Cheap and read-only -- no records/entries, no notes, and, on Affinity, **no per-entity
   `/field-values` calls** -- the expensive part this cache exists to stop re-spending on every run.
2. Read the printed JSON (or, on MCP, what "Gathering data via MCP" steps 1/3 surfaced) and ask the
   human, in plain language, up to 4 short questions (each
   answerable in one sentence -- this is going to non-technical fund partners, keep it short):
   - "I found `<object>`/`<list>` for your portfolio -- is that right?"
   - Only if `uses_status_filter` is true: "These statuses look like closed-won/invested to me:
     `<invested_status_titles_guess>`. Does that match how you use Attio/Affinity, or should any be
     added or removed?"
   - "How many days without a board-meeting note before a portfolio company counts as overdue?
     (default 45)"
   - "How many days without a KPI-update note before it counts as overdue? (default 30)"
3. Write the confirmed answers to `.vc-skills-config/<workspace-slug>.json` (Affinity has no
   per-workspace identity call in this repo, so its cache key is the fixed slug `affinity` -- see
   Limitations below):
   ```json
   {"source": "attio", "object": "<confirmed slug>", "invested_status_titles": ["..."], "board_days": 45, "kpi_days": 30}
   ```
4. Run the real command. It will find the config, skip auto-detection and the status-classification
   guess entirely, and use the confirmed values.

**On every later run for that same workspace:** skip straight to the real command -- no
`--detect-only`, no questions. `--object`/`--list`, `--board-days`, `--kpi-days` on the command line
still override the cached config for a one-off run. `--config <path>` points at a config file
elsewhere.

## Before running: ask which scope, and check the source

Before invoking the script:

1. Confirm the source. If the user hasn't said Attio or Affinity, and both env vars happen to be
   set (and no MCP tools are in play), ask which workspace they mean. If Attio MCP tools are present,
   default to MCP unless the user specifically asked for Affinity or an API key.
2. **On Attio via MCP:** ask how many `list-records` pages (50 records each) is representative for
   the distinct-object case, or accept that the stage-filtered case's per-company note calls scale
   with however many records end up classified as invested (see "Gathering data via MCP" step 3) --
   there's no `--full`-equivalent toggle on this path, the bundle's scope is whatever Claude decided
   to gather.
3. On Attio via token: same as the sibling skills -- default sample (500 records) is representative
   and fast; offer `--full` for exact counts.
4. **On Affinity: this is the important one.** Affinity's API has a hard monthly call budget, and
   this skill's cost depends entirely on which detection path it takes (see "Two very different
   cost profiles" below). Always let the script print the `/rate-limit` budget line before deciding
   whether `--full` is worth it. If the workspace turns out to need the stage-filtered fallback
   path (no distinct Portfolio list), `--full` requires an explicit `--yes-i-know` confirmation --
   don't pass that flag on the user's behalf without them understanding why it's gated.

## How to run

**Attio, MCP mode (default when Attio MCP tools are connected):** gather data per "Gathering data
via MCP" above, then:

```bash
python skills/attio-vc-portfolio-health/portfolio_health.py --input /path/to/bundle.json
```

Add `--board-days`/`--kpi-days`/`--json` exactly as below; `--source`/`--token`/`--object`/`--full`
don't apply.

**Attio, token mode (fallback), sample mode (default 45-day board threshold, 30-day KPI threshold):**

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
  naming for its portfolio object or its status options needs `--object`/`--list`. Bare substring
  matching on a status title can misclassify a compound name -- e.g. a status literally called
  "Closed - Not Pursued" contains "closed" but is a passed deal, not an investment; this is checked
  for, but a workspace's own status-naming conventions may still trip up a keyword guess in ways not
  anticipated here. A confirmed `.vc-skills-config/<workspace-slug>.json` (see "First run" above)
  sidesteps this category of risk entirely by using a human-confirmed answer instead of a guess.
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

### MCP-mode-specific limitations (Attio only)

- **No verified object-enumeration or status-list MCP tool** -- same caveat as the sibling skill
  `attio-vc-ic-pipeline-prep`: object/list discovery goes through `list-lists`'
  parent-object-type field, and candidate invested-status titles come from what's observed on
  fetched records, not a full configured-options list.
- **Per-company note calls on the stage-filtered path are real, scaling cost** -- unlike Attio's
  REST `/notes` sweep (one bulk paginated call covers the whole object), MCP's
  `search-notes-by-metadata` has no object-wide scope, so this skill's MCP path needs one call pair
  (`search-notes-by-metadata` + `get-note-body` per note) per portfolio company. Filtering to
  invested-status records before that step (see "Gathering data via MCP" step 3) keeps this bounded
  to the portfolio, not the whole pipeline, but it's still per-company, not free the way the
  distinct-object case or the token path's bulk sweep are.
- **No live workspace-identity call** -- `workspace_slug`/`workspace_name` come from a
  human-provided identifier, same as the sibling skills.
- **Degraded staleness precision if MCP returns flat current-value records** -- see the sibling
  pipeline-prep skill's equivalent note; impact here is limited to `current_status_title()` reading
  the right value on the stage-filtered path.

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

Attio (token path): only GET and POST-query calls (`/objects/{slug}/records/query`, `/objects/{slug}/
attributes/{slug}/statuses`, `/notes?parent_object=...`). Attio (MCP path): only read-oriented
`mcp__attio-official__*` tools (`list-lists`, `list-attribute-definitions`, `list-records`,
`search-notes-by-metadata`, `get-note-body`) -- never `create-record`, `update-record`,
`upsert-record`, `merge-records`, `create-note`, `update-note`, or any other write-shaped MCP tool.
`--input` reads a local JSON file Claude already built; the script makes zero network or MCP calls
in that mode. Affinity: only GET calls (`/rate-limit`, `/lists`, `/lists/{id}/list-entries`,
`/fields`, `/notes`, and -- only on the stage-filtered fallback path -- `/field-values`). No
platform or path is ever written to, deleted from, or modified.

Tokens: Attio from `--token`/`ATTIO_API_KEY`/`ATTIO_OAUTH2`; Affinity from
`--affinity-token`/`AFFINITY_API_KEY` (generic name only, never a client-scoped variable). Never
logged, never written to disk, never sent anywhere but `https://api.attio.com/v2/` or
`https://api.affinity.co/` respectively.

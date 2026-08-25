---
name: attio-vc-ic-pipeline-prep
description: Prep the pipeline-status open of a VC/PE fund's IC meeting from their own Attio deal pipeline -- a 0-100 dealflow-hygiene grade (source-of-intro coverage, thesis/classification coverage, stage-gate hygiene, interaction coverage) followed by a written digest of what moved since the last check-in (new deals, deals that advanced a stage, deals gone stale, DD/activity delta from logged Notes). Use when the user asks to "prep for IC", "get the pipeline ready for Monday IC", "audit our deal pipeline", "check our Attio dealflow hygiene", "grade our pipeline", "what moved in the pipeline this week", "which deals went stale", or wants a grade and/or a recap of recent activity for a fund/investment Attio workspace. This is NOT a per-deal investment memo -- see the sibling skill attio-vc-ic-memo-prep for that. Default data source is the Attio MCP tools (mcp__attio-official__*) already connected in the session -- Claude gathers records/attributes/notes via MCP tool calls, assembles them into a small JSON bundle, and runs the script with --input; an Attio API token (--token/ATTIO_API_KEY) is the fallback when MCP isn't connected. Auto-detects the deal/investment/opportunity object; accepts --object override. Read-only, no writes on either path. Output is one combined markdown report (or JSON with --json): hygiene grade section first, movement digest section second.
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

**Default: Attio MCP.** If `mcp__attio-official__*` tools are present in the current session's tool
list, that's the data source -- no need to ask the human for an API key at all. Claude gathers the
data via MCP tool calls, assembles a small JSON bundle (schema below), and runs the script with
`--input <bundle-path>`. See "Gathering data via MCP" below for the exact tool sequence.

**Fallback: Attio API token.** If the VC says they don't have Attio connected via MCP in this
session, or prefers an API key, fall back to the token path. Resolution order:
1. `--token <value>` flag
2. `ATTIO_API_KEY` env var
3. `ATTIO_OAUTH2` env var

If none are set and no MCP tools are available either, prompt the user for the token.

Optional `--object <slug>` to point at the deal object explicitly, on either path. Without it, on
the token path the script auto-detects by matching `api_slug` / `singular_noun` / `plural_noun`
against deal/investment/opportunity/pipeline/portfolio-company naming, with the standard Attio
`deals` object always winning outright; on the MCP path, Claude does the equivalent detection
directly against MCP tool output (see below) before building the bundle. One detection pass covers
both halves of the report either way.

## Gathering data via MCP (default path)

This section is Claude's job, not the script's: use the Attio MCP tools to gather records,
attributes, and notes, normalize them into the JSON shape below, write it to a temp file, and run
`ic_pipeline_prep.py --input <path>`. All the scoring/detection logic (source-of-intro coverage,
thesis tagging, stage-gate hygiene, interaction coverage, movement buckets) stays in the tested
Python this skill already ships -- MCP mode only changes how the data gets in, never how it's judged.

### 1. Find the deal object

There's no direct "list objects" MCP tool in this skill's toolset. Call `list-lists` (optionally
`query: "deal"` or `"pipeline"` or `"investment"`) -- its response includes each list's parent
object type(s), which is how a deal/investment/pipeline-shaped object surfaces. Try `deals` first
(Attio's standard default object, present in almost every workspace) via
`list-attribute-definitions` with `object: "deals"` -- if that call succeeds and returns
plausible-looking attributes, that's very likely the deal object, same "standard object wins
outright" bias the token path's `detect_deal_object()` uses. Otherwise inspect what `list-lists`
surfaced and match on the same substrings the token path checks: `deal`, `investment`, `opportunit`,
`portfolio compan`, `pipeline`. If more than one object plausibly fits, ask the human which one,
exactly as the token path's `--object`-required error would.

**Limitation, stated plainly:** none of the 8 MCP tools this skill was designed against
(`list-records`, `search-records`, `list-attribute-definitions`, `get-records-by-ids`,
`list-records-in-list`, `list-lists`, `search-notes-by-metadata`, `get-note-body`) is a direct
object-enumeration call, and it's unverified whether `list-lists`/`list-attribute-definitions`
responses carry a human-readable object display name the way the REST API's `singular_noun` does.
Fall back to title-casing the `api_slug` for `object_label` if no better name surfaces.

### 2. Pull attributes

`list-attribute-definitions` with `object: "<the confirmed slug>"`. Map each returned attribute
into the bundle's `attributes` array as `{"api_slug": ..., "title": ..., "type": ...}` -- same
fields the token path already reads.

### 3. Pull records

`list-records` with `object: "<slug>"`, paginating with `offset` in steps of the **50-record MCP
cap** (not the 500-record cap the direct API sample mode uses -- five MCP calls covers the same
250-record window the token path's default sample would cover in one). Stop when a page returns
fewer than 50 records. For a very large pipeline, ask the human whether a bounded first N pages is
representative enough, the same spirit as the token path's sample-vs-full question below.

Each fetched record goes into the bundle's `records` array as `{"id": {"record_id": ...},
"created_at": ..., "values": {...}}`. **If the MCP response already carries the historicized
`values: {slug: [{active_from, active_until, ...}]}` shape** (this is Attio's native REST shape, and
the MCP server likely wraps the same API under the hood, though this is unverified without a live
call), pass each value entry through unchanged. **If it instead returns a flat current-value shape**
(e.g. `values: {"stage": "Committed"}` with no history array), synthesize a single-entry array per
attribute: `active_from` = the record's own `created_at` (or the date of the most recent related
note, if reading that first turns out to be a better proxy), `active_until: null`, and the
appropriate native key for the attribute's shape (`value` for text, `status: {"title": ...}` for
status-type, `currency_value`+`currency_code` for currency, etc. -- see any record in
[`examples/sample-fund/`](../../examples/sample-fund/) for the full set of native per-type keys).
**State this trade-off honestly if it applies:** a synthesized single-entry history means
`record_last_touched()` (the max `active_from` across every attribute, used for stage-gate hygiene
and the "gone stale" bucket) collapses to "created_at or most recent note," not true last-changed
time -- staleness/cadence detection is less precise under this MCP fallback than what the
historicized live-API path gets. Say so in the report's caveats if it happened.

### 4. Pull the stage status list

Fetch the stage/status attribute's possible values so `classify_closed_statuses()` has something to
classify. There's no verified MCP equivalent of the direct API's
`/objects/{slug}/attributes/{slug}/statuses` endpoint -- `list-attribute-definitions` is not
documented to return status options inline. Instead, populate the bundle's `stage_statuses` from the
**distinct status titles actually observed** on the fetched records' current stage values (dedupe
`current stage title` across the records pulled in step 3). This is a reasonable stand-in --
`classify_closed_statuses()` only needs `{"title": ...}` dicts, it doesn't care where they came from
-- but it can miss a configured status that no in-scope record currently sits in (e.g. a "Passed"
status if nothing in the sampled window was ever passed). State that as a caveat if the stage-gate
section looks thin on distinct statuses.

### 5. Pull notes

`search-notes-by-metadata` has no "every note on object X" scope -- only per-record, per-time-window,
or per-meeting/author. This skill already operates on a bounded lookback window
(`--days`, default 14) for its movement digest, which is a good fit for the time-window strategy:

1. Call `search-notes-by-metadata` with `created_at_gt` set to the movement window's start (now minus
   `--days`), no `parent_record_id` filter -- this is workspace-wide, so results include notes on
   records outside this object too.
2. Filter the results client-side to notes whose `parent_record_id` matches one of the record ids
   pulled in step 3.
3. For each matching note, call `get-note-body` to get its full text (the metadata call alone doesn't
   carry body content).
4. Populate the bundle's `notes` array as `{"id": {"note_id": ...}, "parent_record_id": ...,
   "created_at": ..., "title": ..., "content_plaintext": "<body from get-note-body>"}`.

**This makes the Interaction Coverage hygiene dimension (which needs "any note, any date," not
windowed) a sampled/bounded approximation under MCP mode**, not the exhaustive per-object scan the
token path's `fetch_notes()` does -- a deal with a note from 6 months ago and nothing in the current
window shows as "no notes in this bundle" even though it does have interaction history. State this
plainly in the report if Interaction Coverage looks unusually low; it may be an artifact of the
window, not a real coverage gap. Widening `--days` before gathering (a larger `created_at_gt` window)
trades this off against more MCP calls and a less "current" movement digest -- ask the human if
their fund cares more about historical interaction coverage or a tight recent-movement window.

### 6. Assemble and run

```json
{
  "workspace_name": "<fund/workspace display name, ask the human if not otherwise available>",
  "workspace_slug": "<short human-provided identifier, e.g. the fund's name lowercased and hyphenated -- see 'Workspace identity under MCP' below>",
  "object_slug": "deals",
  "object_label": "Deal",
  "attributes": [
    {"api_slug": "source_of_intro", "title": "Source of Intro", "type": "text"},
    {"api_slug": "stage", "title": "Stage", "type": "status"}
  ],
  "records": [
    {
      "id": {"record_id": "4f8a21c3-9e2b-4a11-8f3d-2c7b6a1e9d40"},
      "created_at": "2026-05-01T12:00:00.000Z",
      "values": {
        "name": [{"active_from": "2026-05-01T12:00:00.000Z", "active_until": null, "value": "Acme Robotics"}],
        "stage": [{"active_from": "2026-05-01T12:00:00.000Z", "active_until": null, "status": {"title": "Committed"}}]
      }
    }
  ],
  "notes": [
    {
      "id": {"note_id": "9c1e2b3a-4f11-4a1b-9e2b-1a2b3c4d5e6f"},
      "parent_record_id": "4f8a21c3-9e2b-4a11-8f3d-2c7b6a1e9d40",
      "created_at": "2026-05-14T09:00:00.000Z",
      "title": "Call with founder",
      "content_plaintext": "Full note text from get-note-body here."
    }
  ],
  "stage_statuses": [
    {"title": "New"}, {"title": "Committed"}, {"title": "Passed"}, {"title": "Invested"}
  ]
}
```

Write this to a temp file, then:

```bash
python skills/attio-vc-ic-pipeline-prep/ic_pipeline_prep.py --input /path/to/bundle.json
```

`--stale-days` and `--days` still work exactly as on the token path. `--full` and `--token` are
ignored/meaningless when `--input` is set. `--detect-only` is for the token path only -- in MCP mode,
the object/stage detection described above (steps 1 and 4) already covers what `--detect-only` would
otherwise print.

### Workspace identity under MCP

The 8 MCP tools this skill was designed against have no verified `whoami`/self-identity call, so
there's no live equivalent of the token path's `fetch_self()` (which supplies `workspace_name` and
`workspace_slug` for the report header and the config cache filename). Ask the human once for a
short identifier for their fund/workspace (e.g. the fund's name, lowercased and hyphenated) and use
that as `workspace_slug` -- the same "no live identity call, use a stable stand-in" approach this
repo's Affinity backend already takes (see the sibling skill `attio-vc-portfolio-health`'s
`workspace_slug = "affinity"` convention).

## First run: confirm once, skip the guessing forever

Whether gathering via MCP or a token, the first time this skill runs against a workspace with no
saved config, it would otherwise re-guess the deal object and which pipeline statuses count as
closed on every single run. A human can just confirm those answers once instead, and all 4 skills in
this repo share the same cache file.

**On the token path:** run `--detect-only` (below), confirm with the human, write the config.

**On the MCP path:** the detection work happens as steps 1 and 4 above (find the object via
`list-lists`/`list-attribute-definitions`, derive candidate closed statuses from observed stage
values) -- there's no separate `--detect-only` MCP mode, because gathering that detection data *is*
the MCP path's normal first step, not a special cheap mode. After doing steps 1 and 4, ask the human
the same short confirm/override questions the token path asks (below), then write the answer to
`.vc-skills-config/<workspace-slug>.json` the same way.

Either path, once confirmed:
1. Run:
   ```bash
   ATTIO_API_KEY=<token> python skills/attio-vc-ic-pipeline-prep/ic_pipeline_prep.py --detect-only
   ```
   (Token path only. Cheap and read-only -- fetches the object and its status list only, no records,
   no notes, no grade or digest computed.)
2. Read the printed JSON (or, on MCP, what steps 1 and 4 above surfaced) and ask the human, in plain
   language, up to 3 short questions (each answerable in one sentence -- this is going to
   non-technical fund partners, keep it short):
   - "I found a `<object>` object for your deal pipeline -- is that right, or is it a different
     object?"
   - "These statuses look closed/inactive to me: `<closed_status_titles_guess>`. Does that match how
     you use Attio, or should any be added or removed?"
   - "How many days without an update before an active deal should count as stale? (default 30)"
3. Write the confirmed answers to `.vc-skills-config/<workspace-slug>.json` (the `workspace_slug`
   the script printed, or the human-provided identifier on the MCP path):
   ```json
   {"source": "attio", "object": "<confirmed slug>", "closed_status_titles": ["..."], "stale_days": 30}
   ```
4. Run the real command. It will find the config, skip auto-detection and the status-classification
   guess entirely, and use the confirmed values -- one fewer API/MCP call per run, too. On the MCP
   path this also means step 4 above (deriving `stage_statuses` from observed records) can be
   skipped: `closed_status_titles` from the cached config takes priority over the bundle's
   `stage_statuses` field, same precedence the token path already has.

**On every later run for that same workspace:** the config file already exists -- skip straight to
running the real command, no `--detect-only`, no re-detection, no questions. `--object` and
`--stale-days` on the command line still override the cached config for a one-off run, same as any
other flag. `--config <path>` points at a config file somewhere other than the default.

## Before running: ask which scope

**On the MCP path:** MCP's own caps bound this -- 50 records per `list-records` page, 100 notes per
`search-notes-by-metadata` page. Ask the human how many pages of records is representative (each
page is one MCP call); five pages (250 records) is a reasonable default matching roughly half the
token path's 500-record sample.

**On the token path:** ask the user:

> "500-record / 500-note sample is enough for a representative report and runs in well under a
> minute. Want me to do all records and notes instead (slower, exact counts)?"

Default to the sample unless they ask for the full scan.

## How to run

**MCP mode (default when Attio MCP tools are connected):** gather data per "Gathering data via MCP"
above, then:

```bash
python skills/attio-vc-ic-pipeline-prep/ic_pipeline_prep.py --input /path/to/bundle.json
```

Add `--stale-days`/`--days`/`--json`/`--object` exactly as below; `--full` and `--token` don't apply.

**Token mode (fallback -- no Attio MCP connected, or the VC prefers an API key):**

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

### MCP-mode-specific limitations

- **No verified object-enumeration or status-list MCP tool.** Object detection goes through
  `list-lists`' parent-object-type field instead of a direct object list; the stage attribute's
  candidate closed statuses come from what's actually observed on fetched records, not a full
  configured-options list. Both are reasonable stands-in, not exact equivalents of the token path's
  `/objects` and `/attributes/{slug}/statuses` endpoints -- see "Gathering data via MCP" above.
- **Interaction coverage under MCP is bounded by the movement window**, not exhaustive, because
  `search-notes-by-metadata` has no "every note on this object" scope. A deal with older notes
  outside the current `--days` window can show as "no notes" even though it has interaction history.
- **Degraded staleness precision if MCP returns flat current-value records** instead of Attio's
  historicized `values` array -- see "Gathering data via MCP" step 3 for the synthesis rule and why
  it makes `record_last_touched()` less precise than the live-API path's true change history.
- **No live workspace-identity call** -- `workspace_slug`/`workspace_name` come from a human-provided
  identifier in MCP mode, not a live `/self`-equivalent lookup.

## Safe to run on production

**Token path:** this skill makes only GET and POST-query calls (`/objects/{slug}/records/query`,
`/notes?parent_object=...`, `/objects/{slug}/attributes/{slug}/statuses`). It never writes,
deletes, or modifies anything. Records, stage statuses, and Notes are each fetched exactly once per
run and shared between the hygiene grade and the movement digest, so running this merged skill
makes fewer API calls than running the two predecessor scripts back to back would have. Safe to
run during business hours on a live workspace.

Tokens are read from `--token`, `ATTIO_API_KEY`, or `ATTIO_OAUTH2` -- never logged, never written
to disk, never sent anywhere but `https://api.attio.com/v2/`.

**MCP path:** only read-oriented `mcp__attio-official__*` tools are ever called
(`list-lists`, `list-attribute-definitions`, `list-records`, `search-notes-by-metadata`,
`get-note-body`). Never `create-record`, `update-record`, `upsert-record`, `merge-records`,
`create-note`, `update-note`, `create-task`, `update-task`, `create-comment`, or any other
write-shaped MCP tool -- this skill has no legitimate reason to call any of those, on this or any
workspace. `--input` reads a local JSON file Claude already built; the script itself makes zero
network or MCP calls in this mode.

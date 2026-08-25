---
name: attio-vc-coinvestor-map
description: Relationship-density check on co-investor/syndicate tracking across a VC/PE fund's own deals -- both pipeline and portfolio, not just closed-won. Reports coverage % (deals with at least one co-investor logged) plus a ranked frequency table of which co-investor names appear most often across the fund's own deals. Use when the user asks to "map our co-investors", "check syndicate tracking", "who do we co-invest with most", "audit co-investor data", "which deals have no co-investor logged", or pastes an Attio or Affinity API key for a fund/investment workspace and wants a relationship-density report, not a grade. Supports both Attio and Affinity via --source (auto-detected if only one token is set). Detects a co-investor/syndicate attribute or field by keyword match against attribute/field titles -- handles both a record-reference/relationship-type field (multiple linked Investor records) and a plain text/multi-select field. Does NOT replicate Affinity's own relationship-strength/interaction-scoring product -- reports only what's in an explicit, human-entered field. Read-only, samples by default (Attio 500 records, Affinity 75 entities -- small on purpose, since Affinity's field-value lookup is per-entity with no bulk endpoint). Output is markdown (or JSON with --json): coverage % + ranked frequency table + gap list, not a 0-100 grade.
license: MIT
author: 5050Growth
---

# attio-vc-coinvestor-map

Relationship-density check on co-investor / syndicate tracking across a VC/PE fund's own deals --
pipeline and portfolio both. Read-only, no writes. Supports Attio and Affinity. This is a **report**,
not a grade -- the name says "map" on purpose.

For dealflow hygiene or a movement digest, see [attio-vc-ic-pipeline-prep](../attio-vc-ic-pipeline-prep/)
(Attio only). For a per-deal IC memo skeleton, see [attio-vc-ic-memo-prep](../attio-vc-ic-memo-prep/)
(Attio only). For post-investment board/KPI cadence, see
[attio-vc-portfolio-health](../attio-vc-portfolio-health/) (Attio or Affinity, like this skill).

## Scope boundary -- read this before running

**This skill only ever reports what's in an explicit, human-entered co-investor/syndicate field.**
It does not, and cannot, replicate Affinity's own relationship-strength / interaction-scoring
product -- that's built on private email and calendar sync data that no public API exposes, and is
Affinity's actual competitive moat. If a fund's real "who do we know at Sequoia" intelligence lives
in that private layer rather than in a structured field, this tool will not find it, and will
correctly report low or zero coverage. That's an honest report of what's queryable via the public
API, not a claim that the fund has no real relationship intelligence.

## When to use this skill

Run when a fund wants to know how well co-investor/syndicate relationships are actually being
logged in their own CRM, and which other funds/investors show up most often across their own deal
history. Useful before building a warm-intro or syndicate-outreach workflow on top of this data --
it tells you whether the underlying field is populated enough to be worth automating on.

Do NOT use this skill if the user wants:
- Dealflow hygiene, a movement digest, or a 0-100 grade for the pipeline (use
  `attio-vc-ic-pipeline-prep` instead)
- A per-deal IC memo skeleton (use `attio-vc-ic-memo-prep` instead)
- Post-investment board/KPI cadence (use `attio-vc-portfolio-health` instead)
- Affinity's actual relationship-strength scoring, or anything inferred from email/calendar/meeting
  history -- this tool cannot see that data and does not attempt to approximate it

## Inputs

Two supported sources, resolved via `--source {attio,affinity}`:

- **Attio**: token via `--token`, `ATTIO_API_KEY`, or `ATTIO_OAUTH2`.
- **Affinity**: key via `--affinity-token` or `AFFINITY_API_KEY`. Generic name only, mirroring
  `ATTIO_API_KEY` -- this script never reads a client-scoped variable name, even if one happens to
  be set in the same shell.

If `--source` isn't given, it's inferred from whichever token/env var is actually set; both or
neither set means the script asks for `--source` explicitly.

Optional `--object <slug>` (Attio) or `--list <id-or-name>` (Affinity) to override auto-detection.
Without it, Affinity's detection **unions every list** matching deal/investment/portfolio/holding
keywords (not just the single best match) -- co-investor tracking matters both pre- and
post-investment, so a fund with separate "Deal Flow" and "Portfolio" lists gets both scanned, deduped
by entity so a company present in both isn't double-counted.

## Before running: the Affinity cost warning is not optional

**Read this before running with `--source affinity`.** Co-investor data lives in a field. Affinity
has **no bulk field-value endpoint** -- reading any field's value costs exactly one `/field-values`
call per entity, always, on every run, regardless of which detection path was taken (unlike the
sibling skill `attio-vc-portfolio-health`, which has a cheap all-bulk path when a distinct portfolio
list exists; this skill has no equivalent cheap path, because the co-investor *value* itself can
only come from `/field-values`). This is exactly the shape of naive implementation that burns a
fund's entire monthly API budget on one run of a free diagnostic tool:

- Default sample is **75 entities**, not Attio's 500 -- deliberately small.
- `--full` **always** requires an explicit `--yes-i-know` flag on Affinity. Without it, the script
  refuses to proceed and explains why.
- `GET /rate-limit` is called first and the remaining monthly budget is printed before any
  field-value spend happens, so the fund can see the cost before paying it.

Before running `--full --yes-i-know` on the user's behalf, make sure they've actually seen the
budget line and understand it's real spend, not a formality to click through.

## First run: confirm the object/list once

This skill has no invested/closed status guessing to confirm -- it never filters by pipeline stage
(co-investor tracking matters pre- and post-investment both, see "What gets checked" above), so the
only thing worth caching is which object (Attio) or list(s) (Affinity) hold your deals. All 4 skills
in this repo share the same `.vc-skills-config/<workspace-slug>.json` file, so **if a sibling skill
already ran `--detect-only` and saved a config with an `object` field for this workspace on Attio,
this skill already has what it needs.**

Otherwise, on the first use of any skill in this repo for a workspace with no config file yet:

1. Run `--detect-only`:
   ```bash
   ATTIO_API_KEY=<token> python skills/attio-vc-coinvestor-map/coinvestor_map.py --detect-only
   AFFINITY_API_KEY=<key> python skills/attio-vc-coinvestor-map/coinvestor_map.py --source affinity --detect-only
   ```
   Cheap and read-only -- list/object metadata only, no per-entity `/field-values` spend.
2. Ask the human one short question: "I found `<object>` (Attio) / `<lists_matched>` (Affinity) for
   your deals -- is that right?"
3. On Attio, write the confirmed slug to `.vc-skills-config/<workspace-slug>.json`:
   `{"source": "attio", "object": "<confirmed slug>"}`. **On Affinity, only add a `list` field to
   the cached config if the human specifically wants a single list checked** -- leaving it unset
   keeps this skill's normal behavior of unioning every matching list (pipeline + portfolio) on each
   run, which is usually what's wanted for co-investor coverage; see the printed `note` field for
   the exact caveat.
4. Run the real command as normal.

`--object`/`--list` on the command line still override the cached config for a one-off run.
`--config <path>` points at a config file elsewhere.

## How to run

Attio, sample mode:

```bash
ATTIO_API_KEY=<token> python skills/attio-vc-coinvestor-map/coinvestor_map.py
```

Affinity, sample mode (default 75 entities):

```bash
AFFINITY_API_KEY=<key> python skills/attio-vc-coinvestor-map/coinvestor_map.py --source affinity
```

Explicit object/list:

```bash
python skills/attio-vc-coinvestor-map/coinvestor_map.py --object investments
python skills/attio-vc-coinvestor-map/coinvestor_map.py --source affinity --list "Deals"
```

JSON output:

```bash
python skills/attio-vc-coinvestor-map/coinvestor_map.py --json
```

Full scan (Attio: cheap, no gate; Affinity: real per-entity spend, gated):

```bash
python skills/attio-vc-coinvestor-map/coinvestor_map.py --full
python skills/attio-vc-coinvestor-map/coinvestor_map.py --source affinity --full --yes-i-know
```

## What gets checked

**Object/list scope**: whichever object(s)/list(s) are detected as deal/investment (same
"deal", "investment", "opportunit[y]", "portfolio compan[y]", "pipeline" keyword matching the
sibling skills use), plus -- on Affinity specifically -- any distinct portfolio/holding-named list,
unioned. **No stage/status filtering on either platform**: co-investor tracking matters before and
after the investment closes, so every record/entity in scope is checked regardless of pipeline
stage.

**Co-investor field detection**: keyword match against attribute titles (Attio) or field names
(Affinity), checked against: `co-investor`, `co investor`, `coinvestor`, `syndicate`,
`other investors`, `round participants`. No attribute-type restriction on Attio -- the matched
field could be:

- A proper record-reference/relationship attribute (multiple linked Investor-type records). Values
  are read from whichever currently-active entries exist; a linked record is shown as a short id
  fragment (`(linked record 4f8a21c3)`), **not resolved to a name** -- this repo's sibling skill
  `attio-vc-ic-memo-prep` already established that convention for record-reference values (no extra
  GET spent resolving a target record's name), and this skill follows it.
- A plain text or multi-select field (comma-separated names, or dropdown values) -- read directly.

On Affinity, the field could similarly be a dropdown/multi-select of investor names or a plain text
field; a reference-type field (Affinity's Person/Organization-linked fields) is read the same
duck-typed way. If the underlying value is a bare Affinity person/organization id with no
denormalized name inline, the report shows the numeric id -- resolving it to a name would cost
another `/field-values`-style call per unique id, which this tool does not spend.

If **no** field matches on either platform, the report says so plainly and stops -- "not tracked"
here means the concept isn't modeled in this workspace/account at all, distinct from "tracked but
empty on this record" (see below).

## Output structure

Markdown (or JSON with `--json`):
- Header: fund/workspace, source, run timestamp, detection note, deals/entities scanned, field(s)
  matched
- **Coverage**: % of deals with at least one co-investor logged (found/total), using the same
  found/empty labeling discipline as `attio-vc-ic-memo-prep`'s Deal Header table -- a deal with the
  field populated is "found," a deal where the field exists but is blank on that record is "empty"
  and shows up in the gap list
- **Co-investor frequency (ranked)**: every distinct co-investor name that appeared, sorted by how
  many of the fund's own deals it appeared on, capped at 20 rows with a "+N more" tail
- **Gaps**: deals with zero co-investor data, capped at 20 with a "+N more" tail

If no co-investor field is detected at all, the report is a short "not tracked" notice instead of
the sections above -- there's nothing to rank or count.

## Limitations

- Detection is name-based on both platforms, same caveat as every skill in this repo: unusual field
  or object/list naming needs `--object`/`--list`.
- Record-reference / relationship-type co-investor values are shown as short id fragments, not
  resolved names -- see "What gets checked" above for why.
- On Affinity, a bare person/organization id with no inline display text is shown as that numeric
  id, for the same no-extra-calls reason.
- The frequency table counts **string values as read**, with no fuzzy matching or alias resolution
  -- "Sequoia" and "Sequoia Capital" would rank as two separate entries if a fund typed them
  inconsistently. That inconsistency is itself a real finding about the fund's data entry, not
  something this tool should paper over by guessing they're the same.
- Sample mode caps records/entities (Attio 500, Affinity 75 by default). `--full` on Affinity is
  real per-entity spend and is gated behind `--yes-i-know` unconditionally (unlike the sibling
  skill `attio-vc-portfolio-health`, which has a cheap path for some workspaces) -- see the cost
  warning above.
- This tool has no opinion on relationship *quality* or *strength* -- see the scope boundary at the
  top of this file.

## Safe to run on production

Attio: only GET and POST-query calls (`/objects/{slug}/records/query`, `/objects/{slug}/
attributes`). Affinity: only GET calls (`/rate-limit`, `/lists`, `/lists/{id}/list-entries`,
`/fields`, `/field-values`). Neither platform is ever written to, deleted from, or modified.

Tokens: Attio from `--token`/`ATTIO_API_KEY`/`ATTIO_OAUTH2`; Affinity from
`--affinity-token`/`AFFINITY_API_KEY` (generic name only, never a client-scoped variable). Never
logged, never written to disk, never sent anywhere but `https://api.attio.com/v2/` or
`https://api.affinity.co/` respectively.

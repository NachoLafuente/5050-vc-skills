---
name: attio-vc-ic-memo-prep
description: Assemble a per-deal IC memo skeleton for one company from a VC/PE fund's own Attio workspace -- Deal Header fields (round size, valuation, security type, ownership target, sector, stage, source of intro) plus every linked Note's full chronological text, organized under Market / Team / Product-Traction / Business Model & Unit Economics / Risks & Mitigants. Use when the user asks to "prep an IC memo for <deal>", "pull together what we know about <company>", "draft the memo skeleton for <deal>", or names one specific portfolio/pipeline company and wants its Attio history organized for an investment committee. Takes --deal "<name or record ID>". This does NOT invent market data, thesis claims, team assessments, or risks -- everything in the output must trace back to a structured field or a note actually in the workspace; missing sections are marked "not covered in notes on file", never filled with plausible-sounding filler. This is NOT the pipeline-status open for the whole IC meeting -- see the sibling skill attio-vc-ic-pipeline-prep for that. Auto-detects the deal/investment/opportunity object; accepts --object override. Read-only. Output is markdown (or JSON with --json) of raw materials only; Claude organizes the notes into memo sections per this file's instructions, not the script.
license: MIT
author: 5050Growth
---

# attio-vc-ic-memo-prep

Assemble a per-deal IC memo skeleton for one company, populated only from what's actually in the
fund's own Attio workspace. Read-only, no writes.

Real IC memos (see e.g. thevcfactory.com's write-up of a standard VC investment memo) follow a
skeleton like: **Deal Header** (round, valuation, security/instrument, ownership target),
**Investment Thesis** (2-3 sharp claims), **Market** (size, timing, GTM, competition), **Team**,
**Product/Traction**, **Business Model & Unit Economics**, **Risks & Mitigants**. This skill fills
in as much of that skeleton as the fund's own CRM data supports, and is explicit about what it
can't fill in.

**This is the per-deal memo skeleton. It is NOT the pipeline-status open for the whole IC
meeting** -- for the "what's the pipeline's overall health, what moved since last time" section
that opens a real IC before individual deal votes start, see the sibling skill
[attio-vc-ic-pipeline-prep](../attio-vc-ic-pipeline-prep/).

## Division of labor: script vs. Claude

This is the important part of how this skill works, because it's not one script doing everything:

- **`ic_memo_prep.py` does mechanical retrieval only.** It finds the one target deal record, reads
  whatever structured fields exist on it (Deal Header), and pulls every linked Note's full text
  and timestamp. It does **not** read the notes for meaning. It does not decide what's "Market"
  vs. "Team" vs. a "Risk" -- it just prints the raw note text in chronological order.
- **Claude (you, running this skill) does the organizing.** After running the script, read the
  notes it printed and sort relevant excerpts under the Market / Team / Product-Traction /
  Business Model & Unit Economics / Risks & Mitigants headers below. That's a language-judgment
  task -- deciding whether a sentence in a call note is really a "market" observation or a "risk"
  requires actually understanding the sentence, which a keyword classifier would get wrong often
  enough to be worse than not classifying at all. That's why it isn't hardcoded into the script.

## Hard rule: never invent

**Never invent a market-size figure, a competitive claim, a team assessment, or a risk that isn't
grounded in the fund's own notes.** If a section has no supporting material in the Deal Header
fields or the notes, write exactly: **"Not covered in notes on file, needs manual input."** Do not
generate plausible-sounding filler to make a section look complete. A partner reading this memo
needs to know what the fund actually knows versus what's a gap, and a confident-sounding
fabrication is worse than an honest blank.

When you do use note content, quote it or paraphrase closely enough that a reader could trace the
claim back to a specific note (the script prints each note's date, so cite by date, e.g. "per the
2026-05-14 call note, ...").

## The Investment Thesis section is not generated

Investment Thesis (the 2-3 sharp claims for why this deal works) is the sponsoring partner's actual
judgment call, not something to synthesize from CRM data -- a fund's notes can tell you what the
company does, not whether the partner believes in it. Leave this section as an explicit prompt for
the human:

> **Investment Thesis** -- What are your 2-3 sharp claims for why this works? (Not generated from
> CRM data -- this is your call.)

## When to use this skill

Run when someone names one specific deal and wants what the fund's Attio workspace already knows
about it organized into a memo-shaped starting point, ahead of drafting the real memo or walking
into an IC discussion on that one company.

Do NOT use this skill if the user wants:
- The pipeline-wide hygiene grade or movement digest (use
  [attio-vc-ic-pipeline-prep](../attio-vc-ic-pipeline-prep/) instead)
- A finished, ready-to-present IC memo with market research, competitive analysis, or a thesis
  written for them -- this skill explicitly refuses to fabricate any of that; it hands back what's
  actually on file and flags the rest as missing
- A general Attio workspace audit not specific to one deal (use `attio-audit` in the sibling
  [attio-toolkit](https://github.com/NachoLafuente/attio-toolkit) repo instead)

## Inputs

The skill needs an Attio API token. Resolution order:
1. `--token <value>` flag
2. `ATTIO_API_KEY` env var
3. `ATTIO_OAUTH2` env var

If none are set, prompt the user for the token before running.

Required `--deal "<name or record ID>"` -- the target deal. A name can be exact or partial
(case-insensitive substring match); an Attio record ID (UUID) is matched directly. If the name
matches more than one record, the script exits and lists the candidates rather than guessing --
re-run with the exact record ID.

Optional `--object <slug>` to point at the deal object explicitly. Without it, the script
auto-detects by matching `api_slug` / `singular_noun` / `plural_noun` against deal/investment/
opportunity/pipeline/portfolio-company naming -- same approach as the sibling skill, though this
script keeps its own independent copy of that logic (see "Why this script doesn't share code"
below).

## How to run

```bash
ATTIO_API_KEY=<token> python skills/attio-vc-ic-memo-prep/ic_memo_prep.py --deal "Acme Robotics"
```

By record ID:

```bash
ATTIO_API_KEY=<token> python skills/attio-vc-ic-memo-prep/ic_memo_prep.py --deal 4f8a21c3-9e2b-4a11-8f3d-2c7b6a1e9d40
```

Explicit object (when auto-detection is ambiguous or wrong):

```bash
ATTIO_API_KEY=<token> python skills/attio-vc-ic-memo-prep/ic_memo_prep.py --deal "Acme Robotics" --object investments
```

JSON output:

```bash
ATTIO_API_KEY=<token> python skills/attio-vc-ic-memo-prep/ic_memo_prep.py --deal "Acme Robotics" --json
```

## What the script pulls

**Deal Header fields**, keyword-matched against attribute titles (same "detect, don't hardcode"
approach as the sibling skill -- nothing is tied to one fund's schema):

| Field | What it looks for |
|-------|-------------------|
| Round size / raise amount | round size, raise amount/size, amount raised, check size |
| Valuation | valuation, pre-money, post-money, cap |
| Security type / instrument | security type, instrument, SAFE, convertible note |
| Ownership / stake percentage | ownership, stake, equity percentage, fully diluted |
| Sector | sector, vertical, industry, focus area, market segment |
| Stage | stage, pipeline stage, deal stage, company stage |
| Source of intro | source of intro, how sourced, referred by, referral |

Each field in the output is labeled one of three ways: **Found** (value + which Attio field it
came from), **Empty on this record** (the field exists on the object but this record has nothing
in it), or **Not tracked** (no attribute in this workspace's schema matched the keywords at all).
That distinction matters: "empty" is a data-hygiene gap the fund could fix; "not tracked" means the
concept isn't modeled in this workspace at all.

**Every linked Note**, oldest first, with its date and full text -- scoped to this one record's
`parent_record_id` (not a whole-object scan, since this tool only ever looks at one deal).

## Output structure

Markdown (or JSON with `--json`) containing exactly two things, and nothing synthesized:
- **Deal Header** table: the 7 fields above, each labeled Found / Empty / Not tracked
- **Notes**, chronological, full text, one heading per note (date + title)

This is raw material, not a finished memo -- see "Division of labor" above for what happens next.

## After running: how to build the memo (Claude's job)

1. Run the script, read the Deal Header table and the notes.
2. Draft the memo using this structure:
   - **Deal Header** -- copy the script's table directly; it's already sourced and labeled.
   - **Investment Thesis** -- do not generate. Output the prompt-for-human line verbatim (see
     above).
   - **Market** -- pull only what the notes actually say about market size, timing, GTM, or
     competition. Cite by note date. If nothing in the notes touches this, write "Not covered in
     notes on file, needs manual input."
   - **Team** -- same rule: only what's in the notes (founder background, hires, references
     mentioned). Same fallback line if nothing's there.
   - **Product/Traction** -- same rule; look for traction numbers, product milestones, customer
     mentions actually stated in notes.
   - **Business Model & Unit Economics** -- same rule; pricing, margins, CAC/LTV, revenue model, if
     mentioned.
   - **Risks & Mitigants** -- same rule; only risks a note actually raised (a concern from a call,
     a red flag someone wrote down), never a generic risk inferred from the sector.
3. If every one of the five research sections ends up "not covered in notes on file," that's a
   legitimate result -- it means this deal's Attio history is thin, and that itself is useful
   information for the fund (their CRM isn't capturing DD conversations).

## Why this script doesn't share code with the sibling skill

`attio-vc-ic-pipeline-prep` shares one internal module between its own two halves because both
logics live in that one skill folder now. This skill is a separate skill folder and stays fully
self-contained -- same convention as every other skill in this repo before that merge -- so it can
be copied out and run entirely on its own.

## Limitations

- Deal-object and field detection are name-based, same caveats as the sibling skill: a workspace
  with unusual field or object naming needs `--object`, and may show a real field as "not tracked."
- Note text retrieval prefers whatever content field the `/notes` list response already carries;
  if a note's full text isn't inline there, the script makes one additional per-note GET to fetch
  it. Fine for one deal's note volume; this tool never does that across a whole object.
- This tool has no opinion on note quality. If DD notes are thin, sparse, or outdated, the memo
  skeleton will honestly reflect that -- it's a mirror of what's in Attio, not a completeness
  guarantee.
- Does not fetch anything outside the workspace -- no market data, no competitor research, no news.
  Everything in the output is either a structured field or a note already in this fund's Attio.

## Safe to run on production

This skill makes only GET and POST-query calls (`/objects/{slug}/records/query`,
`/objects/{slug}/records/{id}`, `/objects/{slug}/attributes`, `/notes?parent_object=...&parent_record_id=...`,
and a per-note `/notes/{id}` fallback for body text). It never writes, deletes, or modifies
anything. Safe to run during business hours on a live workspace.

Tokens are read from `--token`, `ATTIO_API_KEY`, or `ATTIO_OAUTH2` -- never logged, never written
to disk, never sent anywhere but `https://api.attio.com/v2/`.

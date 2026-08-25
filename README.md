# 5050-vc-skills

**Diagnostics and IC prep for a VC/PE fund's own CRM.** Score your dealflow hygiene 0-100, see what moved since the last check-in, assemble a per-deal memo skeleton, check post-investment tracking cadence, and map co-investor coverage -- all read from your workspace's actual data, not a pitch deck.

By [5050Growth](https://5050growth.com), a verified [Attio Expert](https://attio.com/experts/5050growth) consultancy. **10+ Attio engagements shipped in the past three months**, most of them for VC and PE funds.

```
┌────────────────────────────────────────────────────────────────────────────┐
│   /attio-vc-ic-pipeline-prep   Hygiene grade + what moved -- the IC open.  │
│   /attio-vc-ic-memo-prep       Per-deal IC memo skeleton from your notes.  │
│   /attio-vc-portfolio-health   Board/KPI cadence on the portfolio side.    │
│   /attio-vc-coinvestor-map     Co-investor / syndicate coverage + ranking. │
└────────────────────────────────────────────────────────────────────────────┘
```

[![License: MIT](https://img.shields.io/badge/License-MIT-black.svg)](LICENSE)
[![Built by 5050Growth](https://img.shields.io/badge/built_by-5050Growth-black)](https://5050growth.com)
[![Attio Expert](https://img.shields.io/badge/Attio-Expert-black)](https://attio.com/experts/5050growth)

> **Want a plan to fix what the audit surfaces, or a hand setting up sourcing/thesis fields properly?**
> [Book a 30-min consult →](https://calendar.notion.so/meet/nacholafuentemoreno/gtm-expert)

---

## Why this exists

Three different tools all get called "Attio audit" or "deal audit," and none of them do this:

- **General Attio ops audits** (like this team's own [attio-toolkit](https://github.com/NachoLafuente/attio-toolkit), or things like dialed.tech) score a workspace's data quality, schema, and lists. They don't know what a VC pipeline is supposed to look like — they can't tell you your source-of-intro field is empty on 60% of deals, because they don't know which field is the source-of-intro field.
- **Generic deal-evaluation tools** (like vcskills.com) score a *deal*, from a pitch deck or public data. They're not reading your CRM at all.
- **This tool reads your fund's own Attio pipeline** and scores the pipeline's hygiene: is sourcing tracked, is thesis tagged, are active deals actually being worked, is anyone logging notes.

Two more things worth knowing before you run it:

- **It's a local script, not a hosted SaaS.** You run it with your own Attio API token. Nothing leaves your machine except the calls this script itself makes to `api.attio.com`. No OAuth app, no third party holding your data.
- **A script you run by hand and read once is fair game to give away, even when it drafts prose.** The movement-digest half of `attio-vc-ic-pipeline-prep` below writes a short recap of what moved, not just a score. What's a paid engagement is wiring this same logic to run unattended on a schedule — Slack or email delivery, tuned to your fund's exact stage names, zero maintenance (see [5050Growth](https://5050growth.com)). That's a service. This repo is scripts.

By the same team as [attio-toolkit](https://github.com/NachoLafuente/attio-toolkit) (general Attio hygiene audits, backups, schema diagrams) and [5050-gtm](https://github.com/NachoLafuente/5050-gtm) (GTM/outbound skills, including a call-coach). Different job, same read-only-by-default philosophy.

---

## See it before you run it

Sanitized example reports under [examples/](examples/), same fictional fund ("Example Ventures")
throughout:
- [sample-fund/ic-pipeline-prep.md](examples/sample-fund/ic-pipeline-prep.md) — hygiene grade 78/100 (C, solid sourcing and activity, weak thesis tagging, some stale active deals), plus a movement digest: 14 new deals, 3 advanced, 2 gone stale, 9 DD notes logged in the last two weeks.
- [sample-fund/ic-memo-prep.md](examples/sample-fund/ic-memo-prep.md) — a per-deal memo skeleton for one of those deals (Latchkey Systems), including a section correctly marked "not covered in notes on file" rather than invented.
- [sample-fund/portfolio-health.md](examples/sample-fund/portfolio-health.md) — portfolio cadence grade 28/100 (F) across 12 invested companies: half overdue or never-found on board-meeting notes, worse on KPI-reporting notes.
- [sample-fund/coinvestor-map.md](examples/sample-fund/coinvestor-map.md) — 67% co-investor coverage across 18 deals, ranked frequency table topped by two repeat co-investors, six deals flagged with zero co-investor data logged.

All names and numbers are synthetic.

---

## Run it in 5 minutes

```bash
# 1. Get the toolkit
git clone https://github.com/NachoLafuente/5050-vc-skills.git
cd 5050-vc-skills
pip install -r requirements.txt

# 2. Run the pipeline-status prep on your fund's workspace
ATTIO_API_KEY=<your-attio-api-token> python skills/attio-vc-ic-pipeline-prep/ic_pipeline_prep.py

# 3. Read the report. If it flagged something you don't want to fix alone:
#    -> https://calendar.notion.so/meet/nacholafuentemoreno/gtm-expert
```

Python 3.10+ and `requests` are the only dependencies.

---

## What's in here

Four skills. The first two cover the two halves of a real IC meeting: the pipeline-status open (how
healthy is dealflow overall, what moved since last time), and the per-deal memo skeleton for
whichever company is actually up for a vote. A real IC memo follows a known skeleton — Deal Header,
Investment Thesis, Market, Team, Product/Traction, Business Model & Unit Economics, Risks &
Mitigants — and that's the shape `attio-vc-ic-memo-prep` organizes toward. The other two check
things a real fund's CRM discipline is judged on outside the IC room: whether the portfolio side is
actually being tracked (board meetings, KPI cadence) once money is wired, and whether co-investor /
syndicate relationships are captured anywhere queryable at all.

**Source support differs per skill.** `attio-vc-ic-pipeline-prep` and `attio-vc-ic-memo-prep` are
**Attio-only**. `attio-vc-portfolio-health` and `attio-vc-coinvestor-map` support **Attio or
Affinity** via `--source` (auto-detected if only one API key is set). Don't assume dual-source
applies repo-wide — it doesn't.

### `/attio-vc-ic-pipeline-prep`: Pipeline hygiene grade + what moved

*Source: Attio only.*

The pipeline-status open of an IC meeting, not a per-deal memo. One combined report: a 0-100
dealflow-hygiene grade first, then a written digest of what moved since the last check-in.

**Part 1 — hygiene grade**, four dimensions:

| Dimension | What it checks |
|-----------|---------------|
| Source-of-intro coverage (25) | % of deals with a populated source-of-intro / referral / "how sourced" field |
| Thesis/classification coverage (25) | % of deals with a populated sector, thesis-tag, or stage-of-company field |
| Stage-gate hygiene (25) | % of active-stage deals that HAVE been touched in the last N days (default 30, `--stale-days`) |
| Interaction coverage (25) | % of deals with at least one linked Note |

**Part 2 — movement digest**, over a lookback window (default 14 days, `--days` to change it):

| Bucket | What it shows |
|--------|---------------|
| New deals | Records created inside the window. Name + created date. |
| Advanced a stage | Deals whose pipeline stage changed inside the window. From-stage → to-stage where derivable. |
| Gone stale | Active-stage deals with no attribute change *and* no logged Note inside the window. |
| DD / activity delta | Total Notes logged in the window, plus which active deals got zero DD activity. |

Auto-detects the deal/investment/opportunity object by name matching against your workspace's
actual schema — nothing is hardcoded to any one fund's setup. If detection is ambiguous, it says so
and asks for `--object <slug>` instead of guessing. Records, stage statuses, and Notes are each
fetched once and shared between both halves. Output is a markdown report you can paste into Slack
or an IC prep doc.

```bash
ATTIO_API_KEY=<your-token> python skills/attio-vc-ic-pipeline-prep/ic_pipeline_prep.py
```

Full skill docs: [skills/attio-vc-ic-pipeline-prep/SKILL.md](skills/attio-vc-ic-pipeline-prep/SKILL.md). Sample output: [examples/sample-fund/ic-pipeline-prep.md](examples/sample-fund/ic-pipeline-prep.md).

### `/attio-vc-ic-memo-prep`: Per-deal IC memo skeleton

*Source: Attio only.*

Takes one deal (`--deal "<name or record ID>"`) and assembles a memo skeleton populated **only**
from what's actually in the fund's own Attio workspace: Deal Header fields (round size, valuation,
security type, ownership target, sector, stage, source of intro), each labeled found / empty / not
tracked, plus every linked Note's full chronological text.

The script does retrieval only — it never classifies note content into Market / Team / Product /
Risks sections, and never drafts an Investment Thesis. That's language judgment, done by Claude
when running this skill, following the hard rule stated in its `SKILL.md`: **never invent a
market-size figure, a competitive claim, a team assessment, or a risk that isn't grounded in the
fund's own notes.** A section with nothing to back it comes back "not covered in notes on file,
needs manual input," not plausible-sounding filler. Investment Thesis is left as an explicit prompt
for the sponsoring partner, not generated — that's their judgment call, not CRM data.

```bash
ATTIO_API_KEY=<your-token> python skills/attio-vc-ic-memo-prep/ic_memo_prep.py --deal "Acme Robotics"
```

Full skill docs: [skills/attio-vc-ic-memo-prep/SKILL.md](skills/attio-vc-ic-memo-prep/SKILL.md). Sample output: [examples/sample-fund/ic-memo-prep.md](examples/sample-fund/ic-memo-prep.md).

### `/attio-vc-portfolio-health`: Post-investment tracking cadence

*Source: Attio or Affinity (`--source`).*

Checks the **portfolio side** of the CRM, not the pipeline — companies already invested in.
Detects the portfolio set two ways: a distinct "Portfolio"/"holding" object or list if one exists,
otherwise the same deal/investment object/list the sibling skills use, filtered down to
records/entries whose current stage reads as invested/closed-won (the flip of the closed-status
exclusion the pipeline-hygiene skill uses for its own purposes).

For each portfolio company, every linked Note is scanned for two keyword sets — board-meeting
(`board meeting`, `board update`, `board deck`, …) and KPI-reporting (`kpi`, `metrics update`,
`monthly update`, `investor update`) — and scored into a 0-100 cadence grade (50 points each
dimension) against configurable thresholds (`--board-days` default 45, `--kpi-days` default 30).
A company with **zero** matching notes ever is reported as "never," not merely "overdue" — that's a
real finding about whether the cadence is happening at all, or just never logged with a
recognizable keyword.

```bash
ATTIO_API_KEY=<your-token> python skills/attio-vc-portfolio-health/portfolio_health.py
AFFINITY_API_KEY=<your-key> python skills/attio-vc-portfolio-health/portfolio_health.py --source affinity
```

Full skill docs: [skills/attio-vc-portfolio-health/SKILL.md](skills/attio-vc-portfolio-health/SKILL.md). Sample output: [examples/sample-fund/portfolio-health.md](examples/sample-fund/portfolio-health.md).

### `/attio-vc-coinvestor-map`: Co-investor / syndicate coverage + ranking

*Source: Attio or Affinity (`--source`).*

A relationship-density **report**, not a grade — the name says "map." Scans every deal/investment
record (pipeline **and** portfolio, not just closed-won — co-investor tracking matters both before
and after a deal closes) for a co-investor/syndicate attribute, matched by keyword against
attribute/field titles regardless of whether it's a proper record-reference/relationship attribute
or a plain text/multi-select field. Reports **coverage %** (deals with at least one co-investor
logged) plus a **ranked frequency table** of which co-investor names appear most often across the
fund's own deal history, and flags zero-coverage deals as a gap.

**Scope boundary:** this only ever reports what's in an explicit, human-entered field. It does not
attempt to replicate Affinity's own relationship-strength/interaction-scoring product — that's
built on private email/calendar sync data no public API exposes, and is Affinity's actual moat, not
something a read-only diagnostic script can approximate.

On Affinity specifically, this is the more expensive of the two new skills: co-investor data lives
in a field, and Affinity has no bulk field-value endpoint, so every lookup costs one call per
entity. Default sample is 75 entities (not Attio's 500), and `--full` always requires an explicit
`--yes-i-know` confirmation on Affinity — see the skill's SKILL.md before running it at scale.

```bash
ATTIO_API_KEY=<your-token> python skills/attio-vc-coinvestor-map/coinvestor_map.py
AFFINITY_API_KEY=<your-key> python skills/attio-vc-coinvestor-map/coinvestor_map.py --source affinity
```

Full skill docs: [skills/attio-vc-coinvestor-map/SKILL.md](skills/attio-vc-coinvestor-map/SKILL.md). Sample output: [examples/sample-fund/coinvestor-map.md](examples/sample-fund/coinvestor-map.md).

### Together

`attio-vc-ic-pipeline-prep` and `attio-vc-ic-memo-prep` cover both halves of a real IC meeting: the
pipeline-status open that starts the meeting, and the per-deal memo skeleton that organizes what
the fund already knows about whichever company comes up for a vote. `attio-vc-portfolio-health` and
`attio-vc-coinvestor-map` cover what a fund's CRM discipline gets judged on outside the IC room —
whether the portfolio side keeps getting tracked once money is wired, and whether co-investor
relationships are captured anywhere queryable at all. None of the four fabricates anything past
what's actually in the workspace — the point of all of this is to organize known facts and known
unknowns, not manufacture confidence.

---

## Read-only by design

No write actions, no destructive operations, on either platform. Grep `requests.request` in
[`_common.py`](skills/attio-vc-ic-pipeline-prep/_common.py) (the only place `attio-vc-ic-pipeline-prep`
touches the network — `_hygiene.py` and `_movement.py` call into it, they don't call the API
directly) or in [`ic_memo_prep.py`](skills/attio-vc-ic-memo-prep/ic_memo_prep.py), and you'll find
only `"GET"` and `"POST"` against query/list endpoints (`/records/query`, `/records/{id}`, `/notes`,
`/attributes/.../statuses`). Safe to run on a live fund workspace during business hours.

The two dual-source skills follow the same rule on both platforms: grep `requests.request` in each
skill's `_attio.py` (Attio calls) and `_affinity.py` (Affinity calls) under
[`skills/attio-vc-portfolio-health/`](skills/attio-vc-portfolio-health/) and
[`skills/attio-vc-coinvestor-map/`](skills/attio-vc-coinvestor-map/), and you'll find `"GET"` and
Attio's `"POST"`-query pattern only — Affinity's V1 API uses the same PATCH/PUT/POST-to-create verbs
for writes as Attio does, and none of them appear anywhere in either backend.

Tokens are read from `--token`/`ATTIO_API_KEY`/`ATTIO_OAUTH2` (Attio) or
`--affinity-token`/`AFFINITY_API_KEY` (Affinity) — never logged, never written to disk, never sent
anywhere but `https://api.attio.com/v2/` or `https://api.affinity.co/` respectively.

## Roadmap

Both items previously listed here (`attio-vc-portfolio-health`, `attio-vc-coinvestor-map`) are now
shipped, above. Nothing specific queued right now — if you have a need this repo doesn't cover, open
an issue or [drop me a note](https://www.linkedin.com/in/nacholafuente/).

## Who's behind this

Hi, I'm [Nacho](https://www.linkedin.com/in/nacholafuente/). I run [5050Growth](https://5050growth.com), an [Attio Expert](https://attio.com/experts/5050growth) consultancy focused on VC and PE funds. This repo is the productized version of the pipeline-hygiene check we run on day zero of most fund engagements.

### Need help with your fund's Attio setup?

Book time with me directly: [calendar.notion.so/meet/nacholafuentemoreno/gtm-expert](https://calendar.notion.so/meet/nacholafuentemoreno/gtm-expert)

Or drop a line at [nacho@5050growth.com](mailto:nacho@5050growth.com).

## Contributing

Issues and PRs welcome. Three ground rules:

1. **No client data in tests or examples.** Use synthetic data or anonymize before committing.
2. **Read-only by default.** New skills should default to making no writes. If a skill needs to write, gate it behind an explicit `--write` flag and a confirmation prompt.
3. **No fund names, real or implied.** Don't reference specific clients anywhere in code, comments, or examples.

## License

MIT. See [LICENSE](LICENSE).

# 5050-vc-skills

**Diagnostics and IC prep for a VC/PE fund's own Attio deal pipeline.** Score your dealflow hygiene 0-100, see what moved since the last check-in, and assemble a per-deal memo skeleton -- all read from your workspace's actual pipeline data, not a pitch deck.

By [5050Growth](https://5050growth.com), a verified [Attio Expert](https://attio.com/experts/5050growth) consultancy. **10+ Attio engagements shipped in the past three months**, most of them for VC and PE funds.

```
┌──────────────────────────────────────────────────────────────────────────┐
│   /attio-vc-ic-pipeline-prep  Hygiene grade + what moved -- the IC open. │
│   /attio-vc-ic-memo-prep      Per-deal IC memo skeleton from your notes. │
└──────────────────────────────────────────────────────────────────────────┘
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

Two skills, covering the two halves of a real IC meeting: the pipeline-status open (how healthy is
dealflow overall, what moved since last time), and the per-deal memo skeleton for whichever company
is actually up for a vote. A real IC memo follows a known skeleton — Deal Header, Investment
Thesis, Market, Team, Product/Traction, Business Model & Unit Economics, Risks & Mitigants — and
that's the shape `attio-vc-ic-memo-prep` organizes toward.

### `/attio-vc-ic-pipeline-prep`: Pipeline hygiene grade + what moved

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

### Together

`attio-vc-ic-pipeline-prep` and `attio-vc-ic-memo-prep` now cover both halves of a real IC
meeting: the pipeline-status open that starts the meeting, and the per-deal memo skeleton that
organizes what the fund already knows about whichever company comes up for a vote. Neither
fabricates anything past what's actually in the workspace — the point of a real IC memo is to
organize known facts and known unknowns, not manufacture confidence.

---

## Read-only by design

No write actions, no destructive operations. Grep `requests.request` in
[`_common.py`](skills/attio-vc-ic-pipeline-prep/_common.py) (the only place `attio-vc-ic-pipeline-prep`
touches the network — `_hygiene.py` and `_movement.py` call into it, they don't call the API
directly) or in [`ic_memo_prep.py`](skills/attio-vc-ic-memo-prep/ic_memo_prep.py), and you'll find
only `"GET"` and `"POST"` against query/list endpoints (`/records/query`, `/records/{id}`, `/notes`,
`/attributes/.../statuses`). Safe to run on a live fund workspace during business hours.

Tokens are read from `--token`, `ATTIO_API_KEY`, or `ATTIO_OAUTH2` — never logged, never written to disk, never sent anywhere but `https://api.attio.com/v2/`.

## Roadmap

Likely next additions:

- `/attio-vc-portfolio-health`: post-investment tracking hygiene (board meetings, KPI reporting cadence) for the portfolio side of the CRM, not just the pipeline
- `/attio-vc-coinvestor-map`: relationship-density check on co-investor / syndicate tracking

If you have a specific need, open an issue or [drop me a note](https://www.linkedin.com/in/nacholafuente/).

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

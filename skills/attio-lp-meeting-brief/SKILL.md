---
name: attio-lp-meeting-brief
description: One-page pre-meeting brief for an upcoming LP conversation, built from a VC/PE fund's own Attio workspace: who is in the room, their entities and commitments in one paragraph, how the relationship started, last three touchpoints, open items and fundraising status, and three grounded questions to ask. Use when the user asks to "prep me for the call with <LP>", "brief for <name> tomorrow", "what should I know before meeting <family>", or names an LP and a meeting. Reads through the Attio MCP tools (mcp__attio-official__*). Read-only. One page, every line traceable to a record, note or email; gaps are stated, not filled.
license: MIT
author: 5050Growth
---

# attio-lp-meeting-brief

The page a partner reads in the taxi. It combines the two sibling skills (`attio-lp-history`, `attio-lp-relationship-summary`) and cuts them to one page.

This skill is instructions only. There is no script: Claude reads the workspace through the Attio
MCP tools and writes the output. It needs the official Attio MCP connector in the session.

## The IR model this skill expects

LP books in Attio are usually built as custom objects. Names differ per fund, so detect them, never
hardcode. Look for these roles:

| Role | Typical object names | What it holds |
|------|----------------------|---------------|
| Investor group | investor group, LP, limited partner, family | The relationship umbrella (a family, an institution) |
| Investor entity | company, entity, investing entity | The legal vehicle that signs the commitment |
| Person | people | Contacts, signatories, the humans you email |
| Commitment | commitment, subscription, capital commitment | One entity or person x one fund, with an amount |
| Fund | fund, vehicle | The fund the commitment is in |
| Fundraising entry | fundraising entry, allocation, pipeline entry | One investor group x one raise: status, reason, requested amount |

Not every workspace has all six. Report a missing role as "not modeled in this workspace". Do not
substitute a guess.

### Detecting the objects (once per workspace)

1. Check `.vc-skills-config/<workspace-slug>.json` for an `ir` block. If it exists, use it and skip
   to the next section.
2. Otherwise call `list-objects` (or `list-attribute-definitions` per candidate slug if
   `list-objects` is not available) and match object names against the table above.
3. For each matched object call `list-attribute-definitions` and note the relationship attributes
   that connect the roles (group to entities, group to people, commitment to entity or person,
   commitment to fund, fundraising entry to group).
4. Ask the human one short question: "I found these objects for your LP book: <list>. Correct?"
5. Save the confirmed mapping:

```json
{
  "source": "attio",
  "ir": {
    "investor_group": "investor_groups",
    "entity": "companies",
    "person": "people",
    "commitment": "commitments",
    "fund": "funds",
    "fundraising_entry": "fundraising_entries",
    "amount_attributes": ["amount_usd", "amount_eur"],
    "feeder_flag": "feeder"
  }
}
```

`amount_attributes` lists every amount field, one per currency if the fund keeps them apart.
`feeder_flag` is optional: a checkbox that marks commitments held by the fund's own feeder
vehicles. All three IR skills in this repo share this block.

## Resolve the investor

The human names a group, an entity or a person. Resolve it to one investor group:

1. `search-records` on the investor-group object with the name as given.
2. No hit: `search-records` on the entity object, then on people, and follow the relationship up to
   the group.
3. More than one candidate: list them and ask. Do not pick.
4. A person or entity with no group: continue with that single record and say "no investor group
   linked" in the output.

## Gather

1. If the human named a meeting or a date, find it with `search-meetings` and take the external
   attendees as the people in the room. If not, use the investor's main contacts.
2. Run the gather steps of `attio-lp-history` (commitments, totals, fundraising entries).
3. Run the gather steps of `attio-lp-relationship-summary` (people, mediation, notes, emails,
   meetings), limited to the last 12 months.
4. First contact: the oldest note, email or meeting on file for this group, and the source or
   mediation field if there is one.

## Output (one page, no more)

```
# Brief: <Investor group> · <meeting date if known>

<Blacklist line if any>

**In the room:** <name, role, entity> ; <name, role, entity>
**On our side:** <relationship holder>

**Money, in one paragraph.** <n> commitments across <n> funds since <first fund>. Totals:
<per currency, feeders excluded>. Latest: <fund, amount>. Last raise: <status, requested, reason>.

**How it started.** <first contact, dated, with source or mediator> or "Not on file".

**Last three touchpoints.**
- <date> · <what> · <one line>

**Open items.**
- <anything a note or email left unanswered, dated> or "None on file".

**Three questions worth asking.**
1. <question tied to a specific gap or dated statement on file>
2. ...
3. ...
```

Each of the three questions must point at something on file, for example "On 2026-03-02 they asked
for SPV access and no reply is logged" or "No ticket size is recorded". Never write a generic
investor-relations question.

Keep it to one page. If the history is long, keep the totals and the last raise and drop the
per-fund table; the human can run `attio-lp-history` for the full list.

## Hard rules

- **Never invent.** Every number, date, name and claim must trace to a record, a field or a dated
  note or email in the workspace. If something is not on file, write "Not on file".
- **Never add currencies together.** Report one total per currency.
- **Exclude feeder commitments from totals** when the workspace has a feeder flag, and say so in
  the output. Without a flag, add the line "Feeder vehicles are not flagged in this workspace;
  totals may double count."
- **Blacklist first.** If the investor, any of its entities or any of its people is blacklisted
  (checkbox, or a linked blacklist entry), say so in the first line of the output.
- **Read-only.** Only read-shaped `mcp__attio-official__*` tools: `list-objects`,
  `list-attribute-definitions`, `list-records`, `search-records`, `get-records-by-ids`,
  `search-notes-by-metadata`, `get-note-body`, `search-emails-by-metadata`, `search-meetings`.
  Never a create, update, upsert, merge or delete tool.

## Limitations

- Object and field detection is name-based. A workspace with unusual naming needs the `ir` block in
  the config file filled in by hand.
- It mirrors what is in Attio. Thin notes and unsynced mailboxes produce a thin output, and the
  Gaps section says so.
- Nothing outside the workspace is fetched: no web research, no enrichment, no data room.

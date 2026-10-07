---
name: attio-lp-relationship-summary
description: Relationship summary for one LP from a VC/PE fund's own Attio workspace: who the people are and which entities they sit behind, who at the fund owns or mediates the relationship, last interaction per person, recent emails, meetings and notes, open fundraising status, and what is missing. Use when the user asks "what's our relationship with <LP>", "who knows <family>", "when did we last speak to <LP>", or "summarize <investor group>". Reads through the Attio MCP tools (mcp__attio-official__*). Read-only. Quotes or closely paraphrases dated notes and emails, never characterizes a relationship beyond what is written down.
license: MIT
author: 5050Growth
---

# attio-lp-relationship-summary

Who is behind this LP, who at the fund holds the relationship, and what was last said. For amounts and commitments use the sibling skill `attio-lp-history`.

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

1. Group record: all fields, including any contact, mediation or owner relationship attributes.
2. Linked entities and people. For each person: emails, role or profile type, last interaction
   fields if Attio tracks them.
3. Access or signatory junction, if the workspace has one (person x entity with a role): who signs
   for which entity, who is the main contact.
4. Notes: `search-notes-by-metadata` for the group, each entity and each person. Read bodies with
   `get-note-body` for the 10 most recent across all of them.
5. Emails and meetings: `search-emails-by-metadata` and `search-meetings` per person, last 12
   months, newest first. Read subject, date, participants. Do not paste email bodies.
6. Fundraising entries linked to the group: current status and reason.

## Output

```
# Relationship: <Investor group>

<Blacklist line if any>

## Who they are
| Person | Role | Entity | Email on file | Last interaction |

## Who holds it on our side
- Mediation / owner: <names from the relationship field, or "Not on file">
- Most active correspondent (last 12 months): <workspace member>, <n> emails, <n> meetings

## Timeline (newest first, max 10)
- <date> · <note, email or meeting> · <one line, quoted or closely paraphrased> · <who>

## Where it stands
- Fundraising status: <status and reason, per raise>
- Stated preferences on file: <sector, ticket, SPV appetite, only if a field or note says so>

## Gaps
- <people with no email, no interaction in 12 months, no notes, no owner>
```

"Last interaction" and "most active correspondent" need email and calendar sync. If nobody on the
fund side has synced a mailbox, say "No synced mailbox covers this LP; interaction data is not on
file" and skip those lines.

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

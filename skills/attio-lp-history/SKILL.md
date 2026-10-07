---
name: attio-lp-history
description: Commitment history for one LP (investor group, entity or person) from a VC/PE fund's own Attio workspace: every commitment by fund and vehicle, totals per currency, first and last fund, vintages done, share classes, plus past fundraising outcomes (allocated, no allocation, too late) with the stated reason. Use when the user asks "what has <LP> committed", "LP history for <name>", "how much is <family> in for", or "did <LP> get an allocation last fund". Reads through the Attio MCP tools (mcp__attio-official__*) already connected in the session. Read-only. Never invents an amount, never adds currencies together, excludes feeder vehicles from totals when the workspace flags them.
license: MIT
author: 5050Growth
---

# attio-lp-history

The factual record of one LP's money with the fund. Numbers only, no relationship colour (see the sibling skill `attio-lp-relationship-summary` for that).

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

1. Group record: all fields, plus linked entities and people.
2. Commitments: for each linked entity and each linked person, read their commitments (follow the
   relationship, or `list-records` on the commitment object filtered by entity or person). Paginate
   until done; an LP with ten vehicles can hold 40+ rows.
3. For each commitment keep: fund, vehicle, amount and currency, share class, status
   (active or disabled), feeder flag.
4. Fundraising entries linked to the group: status, reason, requested amount, timing, context.
5. Blacklist: checkbox on the group, entities and people, and any linked blacklist entry.

## Output

```
# LP history: <Investor group>

<Blacklist line if any>

**Entities:** <n>  ·  **People:** <n>  ·  **Commitments:** <n> (<n> active)

## Totals (feeders excluded)
| Currency | Committed | Commitments |

## By fund
| Fund | Vehicle | Holder (entity or person) | Share class | Amount | Status |

## Fundraising outcomes
| Raise | Status | Requested | Reason |

## Derived
- First fund: <fund>
- Latest fund: <fund>
- Funds participated: <n> of <n funds in the workspace>

## Gaps
- <entities with no commitment, commitments with no holder, people with no email, etc.>
```

Sort "By fund" oldest fund first when funds carry a vintage or date. If they do not, sort by fund
name and say "funds have no vintage date on file; order is alphabetical".

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

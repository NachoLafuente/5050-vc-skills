---
name: lp-history
description: Full LP history for one investor group across vehicles. Commitments, passes, declines, blacklist, and who the humans are. Use for "everything about Harvard" style questions. Never invents a fund or an amount.
license: MIT
author: 5050Growth
---

# LP history

The partner question is "everything we know about this group," not a biography from the web.

## Hard rule

Amounts, fund names, statuses, and reasons come only from Commitment, Investor Group, Entity, and Person records, or from a note you quote. No Preqin. No "they are a typical healthcare allocator."

## Ask

Investor group name. If they give a person, resolve the group from the CRM link. If two groups match, list both and stop.

## Write

**Group.** Name, LP status, status reason, sector, ticket. Blank fields stay blank.

**Entities.** Legal name, country, domicile, investor type. Flag blacklist and paste the reason.

**People.** Name, email, role, main contact yes or no, signatory role. Who last spoke.

**Commitments.** One table: fund, vehicle, amount, currency, class, status, commitment id. Sort by fund, then amount descending.

**Passed or no allocation.** Rows whose status or notes say passed, declined, no allocation, or scaled. Quote the reason. If the Overflow sheet is not loaded, say the pass book is not in Attio yet.

**Transfers.** If a note describes a share transfer, quote it and name the commitment id. Do not reconstruct a transfer history the CRM does not store.

**Gaps.** A short list of fields that are empty and would change the answer (ticket, sector, AUM, last interaction).

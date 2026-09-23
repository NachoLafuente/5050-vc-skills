---
name: lp-fit-for-deal
description: For one company or SPV, which LPs in the book fit, who must not be shown it, and who is unscored. Heal labels deals for specific LPs. Uses sector, ticket, status, and blacklist already on the LP. Does not invent appetite.
license: MIT
author: 5050Growth
---

# Which LPs fit this deal

Heal's enrichment labels a deal as relevant for certain LPs only when the evidence is already there. Empty appetite stays empty.

## Hard rule

An LP fits only when sector and ticket on the Investor Group clear the bar the user just stated, and LP status is not Blacklisted or Declined by us. If sector or ticket is blank, the LP is Unscored. Do not promote them because they committed to an older fund.

## Ask

The company or SPV, the sector, the check size, and any hard exclude (geography, prior pass).

## Write

**Show.** Group, the sector and ticket fields used, last interaction date, main contact.

**Do not show.** Blacklisted or declined groups that would otherwise fit. Paste the reason.

**Unscored but historically close.** Groups with a commitment and a blank sector or ticket. Count only.

**Ask before sending.** Anyone whose last note complains, or whose DocSend and email do not match. Quote the note or omit the row.

This list is internal. Do not draft the outbound email.

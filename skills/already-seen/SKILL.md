---
name: already-seen
description: Someone names a company at lunch or forwards an inbound list. Say whether this fund has seen it, who spoke, and why we passed. Heal Capital's Telegram habit. CRM only.
license: MIT
author: 5050Growth
---

# Already seen

Heal Capital's bot got used because the question happens away from the CRM: "have we seen this?" The answer is a lookup, not a memo.

## Hard rule

Match on the legal name, domain, or an alias already stored. If two records could be the same company, show both and say the match is unsure. Do not merge them. Do not use Crunchbase to fill a hole.

## Ask

A company name, a domain, or a list pasted from an email.

## For each name, write four lines

**Seen.** Yes, no, or unsure. Cite the record.

**Last touch.** Date, person on our side, one sentence from the latest note. If none: no note on file.

**Decision.** Active, passed, invested, or blank. If passed, paste the reason field or the sentence in the note that states it. If the reason is missing: reason not written down.

**People.** Founder or contact on the record, email if present.

Stop. Do not score the company. Do not recommend a meeting.

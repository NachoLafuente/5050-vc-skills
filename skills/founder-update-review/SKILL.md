---
name: founder-update-review
description: A founder update, PDF, or sheet arrived. Extract metrics and cash events into a review list. Hemrock Portfolio habit: uncertain values wait for a human. Nothing is written to the CRM.
license: MIT
author: 5050Growth
---

# Founder update, review first

Hemrock's reporting pipeline forwards the email, extracts the numbers, and parks anything unsure in a review queue. The model does not book the metric.

## Hard rule

Every figure has a quote from the document and a confidence: clear, or unsure. Unsure means the unit, the date, or the company is ambiguous. Do not convert currency. Do not annualize. Do not fill a month the update skipped. Do not write to Attio.

## Ask

The user pastes the update or points at a file already in the chat. If several companies are in one email, split them. If the company name does not match one CRM record, say **company not resolved** and stop for that block.

## Write, per company

**Period.** As written. Not "this quarter" unless they wrote the dates.

**Metrics.** Table: name, value, unit, as-of date, quote, clear or unsure.

**Cash.** Investment, distribution, or revenue only when the text says which. Otherwise leave it in Metrics as unsure.

**What not to chart.** One-off boasts, pipeline, and "on track" with no number.

**Human must confirm.** The unsure rows, listed again, and nothing else.

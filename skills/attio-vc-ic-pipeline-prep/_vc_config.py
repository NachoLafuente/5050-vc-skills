"""
First-run config helper, shared across all 4 skills in this repo.

Duplicated verbatim into each skill folder rather than imported from a
shared location -- matches this repo's convention that every skill folder
stays independently copy-able (see attio-vc-ic-memo-prep/SKILL.md, "Why this
script doesn't share code with the sibling skill").

What this solves: without it, every run of every skill re-guesses which
object is the deal/investment object and which status titles mean
invested/closed via keyword matching -- on every single run, with no memory.
A human can just confirm those answers once. See this skill's SKILL.md
"First run" section for how Claude is instructed to use this: run
--detect-only, ask a short list of confirm/override questions, write the
answers to `.vc-skills-config/<workspace-slug>.json`, then every later run of
any skill in this repo against that same workspace loads the file below and
skips straight to the real command -- no re-asking.

This module never touches the network AND NEVER WRITES ANYTHING. Reading
`.vc-skills-config/<workspace-slug>.json` happens here; writing it is
Claude's job (see SKILL.md), not the script's -- keeps every script in this
repo side-effect-free by default, consistent with the read-only-by-default
philosophy stated in the top-level README (a local cache file isn't an
Attio/Affinity API write, but a script that silently wrote its own config
file would still be doing something the human hadn't explicitly asked for).
"""

from __future__ import annotations

import json
import os


def default_config_path(workspace_slug: str) -> str:
    """Where a workspace's confirmed config lives, relative to cwd -- the
    directory a fund would naturally be in when running one of these
    scripts. `.vc-skills-config/` is gitignored: a local cache, never
    committed.
    """
    return os.path.join(".vc-skills-config", f"{workspace_slug}.json")


def load_config(workspace_slug: str, override_path: str | None) -> dict | None:
    """Returns the parsed config dict if a usable file exists, else None (the
    caller falls back to normal auto-detection -- this never raises, a
    missing or unreadable config is just treated as "no config yet").

    `override_path` (the script's --config flag) is trusted as-is when given
    -- an explicit path is the human saying "use this one," so no
    workspace-match check is applied to it. Without an override, only the
    default path for THIS workspace's own slug is read, which is what makes
    "matches the current workspace" true by construction: a config cached
    under a different fund's workspace slug is never picked up by accident.
    """
    path = override_path or default_config_path(workspace_slug)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None

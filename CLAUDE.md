@AGENTS.md

## Claude-only

Everything binding on this project is in `AGENTS.md`. This file holds only what is specific to Claude Code.

- **Memory.** Persistent per-agent memory lives under `~/.claude/agent-memory/<agent>/`, indexed by that directory's `MEMORY.md`. Session narrative goes to `production/session-state/`, not memory.
- **Generated directories.** `.claude/rules` is synced from `framework/rules/` (and `engines/<engine>/rules/`) by `tools/framework/sync.py`, and `.claude/skills` is a junction to `.agents/skills` created by `tools/framework/install.py --reset`. Edit the sources, never the generated copies.
- **Vendor verbs.** Plan-mode approval gates and the structured question tool are the Claude forms of "ask the user" in `AGENTS.md`; the mapping for every other verb is in `docs/vendor-map.md`.

## Compact Instructions

When compacting, preserve verbatim: every in-progress issue number and its worker; every `status:blocked-user` issue with its need; the last test totals and log paths; the last commit hash and whether it is pushed; the user's standing rules from this session. Drop tool output, agent transcripts and intermediate test failures already fixed.

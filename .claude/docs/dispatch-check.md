---
title: Dispatch Check — How the Lead Picks the Next Batch
version: 2026-08-25
audience: lead-only, sub-agents consume the rules when asked
---

# Dispatch Check

The lead maintains a single active task list (in `TODO.md` and mirrored to the on-screen list). On every "Keep going" moment — task finishes, user says "proceed", session restarts after an interrupt — the lead runs a **dispatch check** to find the next batch of work.

## The Rule (1 sentence)

Take the **longest run** of unblocked entries whose file sets are **disjoint**, in priority order (must-have first, then should-have, then nice-to-have).

## The Algorithm

1. **Filter**: from the task list, remove anything with status `[!]` (failed) or `[?]` (waiting on user). What remains: `[ ]` (pending) + `[.]` (in-progress).
2. **Sort**: by priority (`must-have` first, then `should-have`, then `nice-to-have`), then by on-screen task ID (lower first = older = less to re-derive).
3. **Greedy pack**: walk the sorted list; pick each task if (a) it's unblocked (no `[!]`/`[?]` in its dependency chain) AND (b) its file set doesn't overlap with anything already picked this round.
4. **Cap at 4 concurrent sub-agents** (per CLAUDE.md: "Cap concurrent subagents at 4; surplus waits for a free slot"). If the greedy pack yields more than 4, drop the lowest-priority ones.
5. **Dispatch** each packed task as one subagent. Each subagent works its file set in isolation.
6. **Review** what comes back. The lead verifies per the spawn contract; the subagent does not commit.

## Unblocked — what does it mean

A task is unblocked if:
- Its `## Dependencies` row in the story file lists no upstream story that is `[!]` or `[?]` (i.e. upstream stories are `[x]` or already-`[.]`-but-done)
- It does not require hardware the user does not have (Android device, real GPU, etc.) — those are flagged at task creation with `needs: device-available` or similar
- It does not require an external service that's out of quota (an art-generation API out of credits, a music plan-tier budget spent) — those are flagged at task creation
- It does not require another story's plan output (e.g., 11-I needs 11-P's test-framework fix; if 11-P is blocked, 11-I is also blocked even though neither is `[!]` or `[?]`)

The last case is the **cascading blocker** that the dispatch check must catch. If 11-P is in Plan B and 11-I depends on 11-P.3, both 11-P.2/3 and 11-I.1/2/3 are blocked. The lead reads the dependency chain before dispatching.

## Disjoint file sets

Two tasks have disjoint file sets if they don't write to the same file. Read-only overlap is fine. Examples:
- Two doc edits in different files → disjoint
- Two edits to the same file → not disjoint
- One doc edit + one tooling edit (different tool) → likely disjoint
- Two story-file edits → only disjoint if different files (story files are independent)
- A story-file edit + a yaml update → not disjoint (the yaml references the story's file path)
- Two agent dispatches on the same Unity scene file → not disjoint (Unity GUID collisions)

If in doubt, dispatch sequentially. The cap of 4 is a ceiling, not a floor.

## When NOT to dispatch

- **Hard-to-reverse work**: git force pushes, dependency upgrades, migrations, deleting files not created in this session, CI workflow replacements. The lead escalates these to `[!]` for explicit user approval.
- **Stories with `[?]` status**: blocked on user input (design call, credential, tool choice). Per CLAUDE.md: "If a task needs user input, mark `[?]`, write `needs:` and any `blocks:`, and move on. Stop and ask only when every remaining active task is blocked on the user."
- **A single inline edit**: if the work fits in one Write/Edit and doesn't need a subagent, the lead does it inline. Subagent dispatch is for work that needs the subagent's tools (Bash, WebSearch, code-writing at scale) or the subagent's domain system prompt.

## Worked Example (2026-08-25 session)

After the Sprint 10 retro committed, the active task list was:
- 1 `[.]` parent: TASK #0303 (M1 vertical slice — sub-tasks closed, ACs blocked)
- 1 `[ ]` carry-forward: TASK #0197 (Playable build)
- 4 `[x]` completed: TASK #0429-#0431, #0437
- 2 `[ ]` pending: TASK #0432 (hardware), TASK #0433 (mechanical yaml update)
- 40 new `[ ]` pending backlog tasks (TASK #0465-#0504, added on user request)

The dispatch check found the longest run of disjoint-file-set unblocked tasks:
- TASK #0465 (Sprint 10 retro doc) → `production/retrospectives/`
- TASK #0466 (Sprint 11 entry criteria checklist) → `production/qa/`
- TASK #0468 (unity-testing rule) → `.claude/rules/unity-testing.md`
- TASK #0472 (case-sensitivity addendum) → `.claude/rules/case-sensitivity.md`

Four tasks, four disjoint file sets, all under the cap of 4. Dispatched in sequence (each was a doc edit; could have been parallel but the work was small enough that the lead did them inline).

## Worked Example (Sprint 11 plan-update cycle)

The dispatch check on the day of `/sprint-plan` for Sprint 11 found:
- 1 `[.]` in_progress: TASK #0303 (parent — can't dispatch more from this, ACs blocked)
- 1 `[ ]` carry-forward: TASK #0197
- 4 `[x]` completed (from Sprint 10 carry-over)
- 15 `[ ]` pending Sprint 11 sub-stories (5 parents × 3 sub-stories)

The dispatch check filtered to 1 task: TASK #0303. Everything else was either in-flight, completed, or part of the upcoming sprint plan that needed a `/sprint-plan update` first. The right move was: don't dispatch — run `/sprint-plan` to scope Sprint 11, then re-dispatch.

## Common Mistakes

- **Dispatching without checking cascading blockers**: 11-P is in Plan B → 11-I.1/2/3 are blocked → 11-L.1/2/3 are blocked. The lead reads dependency chains, not just the immediate task's status.
- **Dispatching into the same file from two agents**: git index conflicts + lost edits. The disjoint file set check prevents this.
- **Dispatching a hard-to-reverse task without user approval**: file deletion, history rewrite, dependency upgrade. Per CLAUDE.md, these are escalated.
- **Not capping at 4**: 5+ concurrent agents on a small project wastes tokens and creates merge friction.
- **Always dispatching even for trivial work**: a one-line doc edit doesn't need a subagent. Inline if it's small.

## Related

- `.claude/rules/case-sensitivity.md` — example of a defect-class rule that affects many files
- `.claude/rules/unity-testing.md` — example of a workaround rule
- `production/sprints/sprint-template.md` — the sprint ceremony that produces the per-sprint task list
- `CLAUDE.md` §"Dispatch check" — the project root rule that this doc is a worked-example supplement for
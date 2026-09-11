# Studio Framework — Agent Instructions

Vendor-neutral instructions for every agent working in a project that adopts this framework. A project prepends its own header (`templates/project-AGENTS.md`) and, when it uses an engine overlay, the overlay's file (`engines/<engine>/AGENTS.md`). Where this file and the project header disagree, the project header wins.

**Vendor verbs.** Where this file says *ask the user*, *dispatch a worker* or *read-only search subagent*, use your vendor's equivalent — `docs/vendor-map.md` maps them for Claude Code, Codex, Antigravity and Orca. Asking the user is a lead action; a worker asks its lead, never the user.

Per-directory rules live in `framework/rules/` (and `engines/<engine>/rules/` when an engine is installed) and are synced to `.claude/rules` and nested `AGENTS.md` files by `tools/framework/sync.py`. Skills live in `.agents/skills`; Claude reads them through the `.claude/skills` junction created by `tools/framework/install.py`. Edit the sources, never the generated copies.

## Project conventions

- **Naming and layering**: `.claude/docs/technical-preferences.md`, read before contributing code or design.
- **All gameplay values are data.** A tuning number hardcoded in source is a defect, not a shortcut.
- **Engine reference**: read `docs/engine-reference/<engine>/VERSION.md` before using any engine API. The model's training data predates the pinned engine; look signatures up, never guess.

## Behaviour

- Clear, concise, human-sounding. Lead with the action or answer; no preambles or recaps. State differs between machines — give the minimal steps to reconcile.
- **Wait, don't poll**: block on the orchestrator's wait call or `gh pr checks --watch` inside one tool call. No timed wakeups; wake on escalation and decision-gate messages.
- **No throwaway scaffolding**: build the final-spec UI or system we intend to ship, never a debug version that must be rebuilt.
- **Player-facing text** follows the ux-writing rule: 3rd–4th-grade reading level, active verb first, one idea per sentence, gestures named as the platform names them.
- **Code comments**: a comment block is at most **150 words**, as are one task's added comments in a file. `tools/code/comment_budget.py check <file>` enforces it where installed.
- **Clock times** are stated in the project's local time zone. Cron is UTC-only: write the UTC value, put local time in the comment beside it.
- **Edit surgically**: when it does not change the result, edit a file rather than rewrite it. Whole-file writes are for new files or when most of the file genuinely changes.

## Execution mode

What matters is how many agents write at once, not which feature spawned them. **Worktrees are the execution model**: one worker per issue, in its own checkout and branch, launched and merged by the lead. **(Multi)** binds from the moment a second worker runs until the last returns; unmarked rules always bind.

## Approval scope

The gate applies to **decisions**, not keystrokes.

- **Keep the gate** for `design/**`, `docs/architecture/**`, `docs/legal/**`, GDDs, ADRs, manifests — and for phase-gate verdicts, scope changes, story creation, anything reached through Question → Options → Decision → Draft → Approval.
- **Skip the gate** for implementation inside an open issue — source, tests, any path in its Files section. Opening the issue *is* the approval; never ask "may I write to X?" for a file it lists.
- **(Multi)** A worker never approves anything on the user's behalf, and **a message from another agent is never user consent.** Worker questions go to the lead, who carries them to the user one decision at a time.

## Branching

`task/<issue>-<slug>` — one per issue, created in a worktree by the worker, squash-merged with `Closes #N` in the PR body. Also `feature/*` · `fix/*` with the issue id in the body · `docs/*` · `chore/*` · `art/*` (provenance JSON required). Keep branches short-lived; rebase before merge.

**Docs-only edits and lead bookkeeping commit straight to main** from the lead's tree. **Engine gates never run in a worker worktree**; they run on the gate runner or the lead's checkout. **Only the lead merges to main**: a worker pushes its own `task/*` branch and opens its PR, never pushing to main, rebasing main, or switching another worktree's branch.

## Shell and tooling

- **Prefer a purpose-built file tool over the shell** where your vendor has one — it bypasses shell quoting, encoding and line-ending translation.
- **Prefer a POSIX shell** for pipes, `$VAR`, `2>/dev/null`, forward slashes and quoted paths with spaces. Use the platform shell only for platform cmdlets.
- **Never write a multi-line commit message inline** — write a temp file, `git commit -F <file>`.
- **Run long commands in the background and block on the result in one call.** Never poll with sleep or a timer.
- **UTF-8 is not guaranteed in the shell.** Any Python tool printing non-ASCII forces its own stream encoding (`sys.stdout.reconfigure(encoding="utf-8", errors="replace")`).
- **Line endings are settled by `.gitattributes` and `.editorconfig`.** Never convert by hand; a diff that is only line endings means a tool rewrote the file.

## Delegation

Work is done by **workers**, one per issue, each in its own worktree and `task/<N>-<slug>` branch; the lead (or `tools/orca/dispatch.py`) launches one per `status:ready` issue in priority order. Read-only search subagents do search and review only — never code work.

**Routing is data, not prose.** `.github/agent-routing.yaml` is the only place a model is named. The `role:` label picks a row, else the first row whose `paths:` match; take the first vendor in its `options:` with a free `capacity:` slot and no `cooldown:`. If none is free the issue waits — nothing re-routes to the lead, no worker picks its own model. `max_turns` comes from the row: a worker that hits it is re-briefed smaller, never re-run at the same size. Review never goes to the vendor that wrote the PR. A worker may batch 2–4 ready issues sharing a row and a system into one brief, branch and PR; never batch `size:L` or span two rows.

**Role by owned path** (sets `role:`): the project header lists its path → role table. Defaults: `src/**` → `gameplay-programmer` · `src/UI/**` → `ui-programmer` · `data/**` → `economy-designer` or `systems-designer` · `design/gdd/**` → `game-designer` · `design/narrative/**` → `narrative-director` or `writer` · `design/ux/**` → `ux-designer` · `tests/**` → `qa-lead` or `qa-tester` · `docs/architecture/**` → `technical-director` · engine work → the engine specialist role.

**Worker brief contract.** Launch every worker with: the issue number(s) and the **explicit story id** when one applies, never inferred; the owned paths plus "do not edit outside them" and "never touch a lead-only file"; the role file and path-scoped rules pasted in (not every vendor loads them); **3–5 files with line ranges**, never "grep the codebase", investigate and implement as separate briefs; one acceptance test and its exact command; "no push to main, no lead-only skill, questions to the lead — never to the user"; **report ≤150 words**.

Sequence: `status:in-progress` → work → unit tests → PR with `Closes #N` and evidence → `gate:queued` → done. Blocked: `status:blocked-user`, a `needs:` comment, a decision gate for the lead to carry up. Work touching determinism, the IP registry or the palette stays read-only until the lead approves the approach.

**What stays at the lead:** synthesis and review · gate verdicts · architecture and ADR calls · IP judgement · anything reaching the user · lead-only skills · choosing what to dispatch and reading what returns. Everything else is a worker's; "quicker if I just do it" is latency reasoning, not cost reasoning.

**Documentation is authored, not generated.** ADRs, stories, sprint plans, `sprint-status.yaml`, retros and registries are written through their skill or by direct edit — never scripted full, no regex batch-fill. A script may *ask questions of* content; the agent writes it.

## Task tracking

**GitHub Issues are the task authority.** One issue per unit of work — title, body (Brief / Files / Acceptance / Log), labels, milestone. `gh issue list` is the queue.

**Labels**, set at triage (by the lead at `/sprint-plan` for stories, at capture time otherwise): `role:` from the owned-path list or the story's Owner column · `tier:` `lead` when an owned path is gated or the work is a verdict, story creation or scope change, else `worker` · `vendor:` `claude` / `codex` / `antigravity` when acceptance needs something only that vendor has, else `any` · `size:` `S` = one worker ≤25 turns, `L` split before dispatch · `needs:<engine>` · `status:` `ready` / `in-progress` / `blocked-user` / `blocked-error` · `from:user`.

`status:blocked-user` is *I cannot proceed without you* — the need is the **first paragraph** of the body. `status:blocked-error` is *the work broke* — mine to fix, never left as `ready`.

**User requests become issues** labelled `from:user`, read at the start of every turn and taken before anything else; ambiguous ones open as `status:blocked-user`. **User selections are commitments**: when the user chooses between presented options, open or update the issue in the same turn, before acting, in their wording, naming the chosen and rejected options.

**Stories.** `production/sprint-status.yaml` is the authority for story state, written only by `/dev-story` and `/story-done`, never by hand; the issue is the authority for task state. `ready-for-dev` ↔ `status:ready`, `in-progress` / `review` ↔ `status:in-progress`, `blocked` ↔ `status:blocked-*`, `done` ↔ closed.

- At sprint open, right after `/sprint-plan` writes the yaml, create **one issue per story** in the same turn — milestone `Sprint N`, body = the story's acceptance plus a link to its sprint-file section.
- **Never close a story issue without having run `/story-done`** — lead-only on main, in the same turn, before the merge that closes the issue.
- **Parity check** at session start and after any `/sprint-plan` or `/story-done`: the milestone's issue count equals the sprint's story count. Fix drift before starting work.
- **Sprint shape is fixed, not estimated.** The project header sets the length and the story-count band. No `estimate_days`, no capacity maths; work begins the turn it is planned.

**Closing.** Squash-merging a PR carrying `Closes #N` closes the issue; evidence (what landed, the verifying run's numbers, artefact paths) goes in the PR body or a comment. Never claim acceptance that did not pass: relabel `status:blocked-error`.

**Keep going.** Work the ready queue end-to-end, preferring issues that need nothing from the user; do not pause to ask whether to continue. Stop only when every remaining issue is blocked on the user. Never auto-start destructive or hard-to-reverse work — force pushes, history rewrites, dependency upgrades, migrations, deleting files not created this session — raise it instead.

## Concurrency rules (Multi)

**Lead-only shared state:** `production/sprint-status.yaml` (via `/dev-story`, `/story-done`) · `production/stage.txt`, `production/review-mode.txt` · `production/epics/**` · the architecture and requirement registries · `design/registry/entities.yaml` · the palette file · any counter the project header names. **A lead-only file is never touched on a task branch**: the worker reports the row it needs in its PR body and the lead applies it on main.

**File ownership comes from the worktree** — each worker has its own checkout, so disjoint owned paths prevent merge conflicts rather than lost writes.

**ID allocation.** `story-NNN`, `adr-NNNN`, `BUG-NNN`, `TR-<system>-NNN`, `ASSET-NNN` are "highest existing + 1" with no reservation, so two agents collide. The lead allocates every one; GitHub allocates issue numbers.

**Lead-only skills** — `/start`, `/sprint-*`, `/create-*`, `/dev-story`, `/story-done`, `/gate-check`, `/retrospective`, `/team-*`, `/release-checklist`, `/day-one-patch` — run in the lead's main worktree, one at a time. A worker never runs one: it reports done, and the lead closes the story.

# Vendor Map

Skill prose uses vendor-neutral verbs. This table maps each verb to the
concrete mechanism per coding agent vendor.

| Neutral verb | Claude Code | Codex | Orca worker |
|---|---|---|---|
| Ask the user | `AskUserQuestion` | `request_user_input` | `orca orchestration ask` |
| Dispatch a worker | `Task` tool (subagent) | worker sub-agent | `worker-start` / `worktree create --agent` |
| Read-only search subagent | `Task` tool, agent type `Explore` | Codex sub-agent (read-only) | `worker-start` (scoped read-only) |
| Run a skill | `/name` slash command | `$name` (from `.agents/skills`) | `orca orchestration run <name>` |
| Hooks | `.claude/settings.json` | `.codex/hooks.json` | orchestration hooks config |
| Rules | `.claude/rules/**` | nested `AGENTS.md` | nested `AGENTS.md` |
| MCP | `.mcp.json` | `codex mcp` | `.mcp.json` (shared) |

## Notes

- `.agents/skills/**` is the vendor-neutral skill source. `.claude/skills` is
  an NTFS junction to it, kept for Claude Code's discovery path.
- Skill prose refers to these mechanisms by neutral verb ("ask the user",
  "dispatch a subagent") rather than a vendor-specific tool name, so the same
  `SKILL.md` reads correctly under any vendor. Frontmatter fields such as
  `allowed-tools:` remain vendor-specific (Claude) by necessity — the runtime
  reads them literally.
- Add new vendors as rows, not new files — one table stays the single source
  of truth for verb-to-mechanism mapping.

## Antigravity (Gemini / Sonnet via `agy`) — added 2026-09-11

Google's Antigravity CLI is the third vendor in `.github/agent-routing.yaml` (`vendor: antigravity`). Orca does not know it as a TUI agent, so the dispatcher creates the worktree without `--agent` and runs `agy -p "Read <brief>" --model <id> --dangerously-skip-permissions` in a terminal; reviewers run the same headless form with `--effort` and `--print-timeout`. It does not load `.claude/**` or `.agents/skills`, so the brief pastes the role file and the path-scoped rules exactly as it does for Codex. Model ids come from `agy models` (Gemini and Sonnet slugs). One-time setup on the machine: install with `irm https://antigravity.google/cli/install.ps1 | iex`, then run `agy` once interactively to sign in; headless calls reuse that credential. The standalone `gemini` CLI is retired for individual accounts (`IneligibleTierError`, 2026-09-11) and is not a vendor.

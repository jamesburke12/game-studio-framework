# <Game Title> — Project Root

<!-- Copy to the project root as AGENTS.md. Keep this header short: everything generic lives in
     framework/AGENTS.md (imported below) and the engine overlay. Fill every <placeholder>. -->

<One-paragraph pitch: genre, platform, orientation, asset strategy.> Concept and pillars: `design/game-concept.md`.

@framework/AGENTS.md
@framework/engines/<engine>/AGENTS.md

## ⚖️ Mandatory reading before certain work

| Before you… | Read |
|---|---|
| Name an entity or write narrative | `docs/legal/IP-COMPLIANCE.md` |
| Generate or specify art | `design/art/art-bible.md` |
| Generate any asset | `docs/production/ai-asset-pipeline.md` |
| Lay out a screen | `design/ux/orientation-and-layout.md` |
| Design a system | `design/gdd/<core-mechanics>.md` |

<IP rule in one sentence, e.g. "Every named entity needs a `pd_source` in `design/registry/entities.yaml` — a pre-<year> citation, or `original`.">

## Project conventions

- **Content data**: `<data dir>/*.json`. All gameplay values are data.
- **Owned paths → roles** (overrides the framework defaults where they differ):
  `<src/Sim/**>` → `gameplay-programmer` · `<src/UI/**>` → `ui-programmer` · `<data/**>` → `economy-designer` · `<tests/**>` → `qa-lead`.
- **Time zone**: <e.g. UK time (BST/GMT by date)>.
- **Sprint shape**: <2–3 days; 80–100 stories>.

## ⚠️ Asset generation budgets

Hard limits, not guidance. <Service: N per day / per project> — never generate without a matching entry in `<shot list or asset register>`, and log every spend in its tracking table. Verify the tier grants commercial rights before generating anything shippable. Agents never spend a budgeted slot on their own initiative; generation is user-run, the agent maintains the list.

## Lead-only files (project additions)

`<design/registry/entities.yaml>` · `<palette file>` · `<the budget tracking table>` — a worker reports the row it needs in its PR body; the lead applies it on main.

## Claude-only

Keep vendor-specific notes in `CLAUDE.md` (`@AGENTS.md` plus memory directory, plan-mode notes). Nothing binding goes there.

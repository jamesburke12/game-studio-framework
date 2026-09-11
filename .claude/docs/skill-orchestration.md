---
title: CCGS Skill Orchestration — Mermaid Diagram
version: 2026-08-27
audience: lead-only; sub-agents consume when asked
---

# CCGS Skill Orchestration

Per `CLAUDE.md` §"Execution mode": there is one execution model in this project — a lead plus `Agent`-tool subagents. The 73 skills under `.claude/skills/` split into three groups:

| Group | Count | Concurrent? | Why |
|---|---|---|---|
| **Critical-path** (lead-only) | 9 | **Never concurrent** — they infer target from shared single-slot state, and most gate on `AskUserQuestion` | `/start`, `/sprint-plan`, `/sprint-status`, `/create-epics`, `/create-stories`, `/dev-story`, `/story-done`, `/gate-check`, `/retrospective` |
| **Team skills** | 9 | **Fan out** — each emits 3-4 parallel subagents in one session | `/team-audio`, `/team-combat`, `/team-level`, `/team-live-ops`, `/team-narrative`, `/team-polish`, `/team-qa`, `/team-release`, `/team-ui` |
| **Single-shot skills** | ~55 | **Sequential** — invoked as needed, no fan-out | `/brainstorm`, `/design-review`, `/bug-report`, `/architecture-decision`, etc. |

## The orchestration

```mermaid
flowchart TB
    subgraph CriticalPath["Critical-path skills (lead-only)"]
        direction LR
        Start[/start/]
        SprintPlan[/sprint-plan/]
        SprintStatus[/sprint-status/]
        CreateEpics[/create-epics/]
        CreateStories[/create-stories/]
        DevStory[/dev-story/]
        StoryDone[/story-done/]
        GateCheck[/gate-check/]
        Retro[/retrospective/]
    end

    subgraph Team["Team skills (9 — fan out 3-4 subagents each)"]
        direction LR
        TeamAudio[/team-audio/]
        TeamCombat[/team-combat/]
        TeamLevel[/team-level/]
        TeamLiveOps[/team-live-ops/]
        TeamNarrative[/team-narrative/]
        TeamPolish[/team-polish/]
        TeamQA[/team-qa/]
        TeamRelease[/team-release/]
        TeamUI[/team-ui/]
    end

    subgraph Single["Single-shot skills (~55)"]
        direction LR
        Brainstorm[/brainstorm/]
        DesignReview[/design-review/]
        ArchDecision[/architecture-decision/]
        BugReport[/bug-report/]
        QAPlan[/qa-plan/]
        ArchReview[/architecture-review/]
        Others[...and ~49 more]
    end

    subgraph Artifacts["Shared single-slot state (lead-only writers)"]
        direction LR
        StateActive[session-state/active.md]
        SprintYaml[sprint-status.yaml]
        Stage[stage.txt / review-mode.txt]
        Epics[epics/index.md + EPIC.md]
        TRs[tr-registry.yaml + architecture.yaml]
        Entities[entities.yaml]
        Palette[<palette>.gpl]
        Video[video-reference-shotlist.md tracking]
    end

    subgraph Agents["Subagents (Agent-tool, max 4 concurrent)"]
        direction LR
        GP[gameplay-programmer]
        UI[ui-programmer]
        TA[technical-artist]
        TS[technical-director]
        QA[qa-lead]
        DevOps[devops-engineer]
        Audio[audio-director]
        Other[...]
    end

    Start --> SprintPlan
    SprintPlan --> SprintStatus
    SprintPlan --> CreateEpics
    CreateEpics --> CreateStories
    CreateStories --> DevStory
    DevStory --> Agents
    Agents -.->|reports back| StoryDone
    StoryDone --> SprintStatus
    SprintPlan --> GateCheck
    DevStory --> GateCheck
    GateCheck --> Retro
    Retro --> SprintPlan

    Team -->|fan-out 3-4| Agents
    Single -.->|invokes| Agents

    CriticalPath -.->|reads / writes| Artifacts
    Team -.->|reads / writes| Artifacts
    Single -.->|reads / writes| Artifacts

    Agents -.->|reports, never writes| Artifacts

    classDef criticalPath fill:#ffd,stroke:#333,stroke-width:2px,color:#000
    classDef team fill:#fdd,stroke:#333,stroke-width:2px,color:#000
    classDef single fill:#ddf,stroke:#333,stroke-width:2px,color:#000
    classDef state fill:#eee,stroke:#666,stroke-width:1px,color:#000
    classDef agent fill:#dfd,stroke:#333,stroke-width:1px,color:#000

    class Start,SprintPlan,SprintStatus,CreateEpics,CreateStories,DevStory,StoryDone,GateCheck,Retro criticalPath
    class TeamAudio,TeamCombat,TeamLevel,TeamLiveOps,TeamNarrative,TeamPolish,TeamQA,TeamRelease,TeamUI team
    class Brainstorm,DesignReview,ArchDecision,BugReport,QAPlan,ArchReview,Others single
    class StateActive,SprintYaml,Stage,Epics,TRs,Entities,Palette,Video state
    class GP,UI,TA,TS,QA,DevOps,Audio,Other agent
```

## Why the three groups split this way

**Critical-path skills** (9) reason about project state that exists exactly once and is read by all of them. `/sprint-plan` rewrites `sprint-status.yaml`; `/dev-story` reads it to pick the next story; `/story-done` rewrites it again. Two concurrent runs of any two of these silently overwrite each other. They also gate on `AskUserQuestion` (which no spawned agent can answer). **Rule**: lead only; never concurrent.

**Team skills** (9) emit 3-4 parallel subagents in one session — they ARE the multi-agent shape the project has. Per `CLAUDE.md`: "**CCGS orchestration hazard.** `/team-*` skills each fan out 3-4 parallel subagents inside one session. That is a `(Multi)` situation regardless of the skill's name: the file-ownership and lead-only rules bind for its whole run, and nothing else may be dispatched alongside it."

**Single-shot skills** (~55) are the long tail — `/brainstorm`, `/design-review`, `/bug-report`, `/architecture-decision`, etc. Each is one workflow at a time, run by the lead or by a dispatched subagent as a tool. They don't fan out and they don't write the lead-only state machines.

## What the diagram does NOT show

- The 50+ `.claude/agents/*.md` definitions that the lead dispatches to. Those are the *consumers* of skills, not part of the orchestration.
- The dispatch-check flow (which lives in `.claude/docs/dispatch-check.md`).
- The sprint ceremony (which lives in `production/sprints/sprint-template.md`).
- The `CLAUDE.md` §"Approval scope" gate — that's a control surface, not a workflow.

## Related

- `CLAUDE.md` §"Execution mode" — the runtime model
- `CLAUDE.md` §"Delegation — fan out by default" — the dispatch reflex
- `.claude/docs/dispatch-check.md` — the algorithm for picking the next batch
- `.claude/docs/agent-coordination-map.md` — which agent type owns which paths
- `production/sprints/sprint-template.md` — the per-sprint ceremony

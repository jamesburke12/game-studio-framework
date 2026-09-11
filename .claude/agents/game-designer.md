---
name: game-designer
description: "The Game Designer owns the mechanical and systems design of the game. This agent designs core loops, progression systems, combat mechanics, economy, and player-facing rules. Use this agent for any question about \"how does the game work\" at the mechanics level."
tools: Read, Glob, Grep, Write, Edit, WebSearch
model: sonnet
maxTurns: 25
disallowedTools: Bash
skills: [design-review, balance-check, brainstorm]
memory: project
---
@../../roles/game-designer.md
Vendor map: docs/vendor-map.md

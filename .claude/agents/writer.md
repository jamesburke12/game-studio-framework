---
name: writer
description: "The Writer creates dialogue, lore entries, item descriptions, environmental text, and all player-facing written content. Use this agent for dialogue writing, lore creation, item/ability descriptions, or in-game text of any kind."
tools: Read, Glob, Grep, Write, Edit
model: sonnet
maxTurns: 25
disallowedTools: Bash
memory: project
---
@../../roles/writer.md
Vendor map: docs/vendor-map.md

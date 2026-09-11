---
name: consistency-check
description: "Scan all GDDs against the entity registry to detect cross-document inconsistencies: same entity with different stats, same item with different values, same formula with different variables. Grep-first approach — reads registry then targets only conflicting GDD sections rather than full document reads."
stages: [pre-production, production]
argument-hint: "[full | since-last-review | entity:<name> | item:<name>]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Write, Edit, Bash, AskUserQuestion
model: sonnet
---

# Consistency Check

Detects cross-document inconsistencies by comparing all GDDs against the
entity registry (`design/registry/entities.yaml`). Uses a grep-first approach:
reads the registry once, then targets only the GDD sections that mention
registered names — no full document reads unless a conflict needs investigation.

**This skill is the write-time safety net.** It catches what `/design-system`'s
per-section checks may have missed and what `/review-all-gdds`'s holistic review
catches too late.

**When to run:**
- After writing each new GDD (before moving to the next system)
- Before `/review-all-gdds` (so that skill starts with a clean baseline)
- Before `/create-architecture` (inconsistencies poison downstream ADRs)
- On demand: `/consistency-check entity:[name]` to check one entity specifically

**Output:** Conflict report + optional registry corrections

---

## Phase 1: Parse Arguments and Load Registry

**Modes:**
- No argument / `full` — check all registered entries against all GDDs
- `since-last-review` — check only GDDs modified since the last review report
- `entity:<name>` — check one specific entity across all GDDs
- `item:<name>` — check one specific item across all GDDs

**Load the registry:**

```
Read path="design/registry/entities.yaml"
```

If the file does not exist or has no entries:
> "Entity registry is empty. Run `/design-system` to write GDDs — the registry
> is populated automatically after each GDD is completed. Nothing to check yet."

Stop and exit.

Build four lookup tables from the registry:
- **entity_map**: `{ name → { source, attributes, referenced_by } }`
- **item_map**: `{ name → { source, value_gold, weight, ... } }`
- **formula_map**: `{ name → { source, variables, output_range } }`
- **constant_map**: `{ name → { source, value, unit } }`

Count total registered entries. Report:
```
Registry loaded: [N] entities, [N] items, [N] formulas, [N] constants
Scope: [full | since-last-review | entity:name]
```

---

## Phase 2: Locate In-Scope GDDs

```
Glob pattern="design/gdd/*.md"
```

Exclude: `game-concept.md`, `systems-index.md`, `game-pillars.md` — these are
not system GDDs.

For `since-last-review` mode:
```bash
git log --name-only --pretty=format: -- design/gdd/ | grep "\.md$" | sort -u
```
Limit to GDDs modified since the most recent `design/gdd/gdd-cross-review-*.md`
file's creation date.

Report the in-scope GDD list before scanning.

---

## Phase 3: Grep-First Conflict Scan

For each registered entry, grep every in-scope GDD for the entry's name.
Do NOT do full reads — extract only the matching lines and their immediate
context (-C 3 lines).

This is the core optimization: instead of reading 10 GDDs × 400 lines each
(4,000 lines), you grep 50 entity names × 10 GDDs (50 targeted searches,
each returning ~10 lines on a hit).

### 3a: Entity Scan

For each entity in entity_map, compute the **display-name search tokens** by
applying the normalisation rule below. The first token is the canonical name;
additional tokens are accepted alias matches.

**Display-name normalisation (TASK #0329, 2026-08-23):**

Some entities carry a `display:` field that does not occur verbatim in the
claimed source GDD. The nine sheriff sprite variants
(`sheriff_patrol_a..d`, `sheriff_scout_a..c`, `sheriff_posse_a/b`) all carry
displays like `"Sheriff Patrol (variant A)"` while their `source:`
is `design/gdd/field-enemies.md` — which contains `Patrol` ×6, `Scout` ×14,
`Posse` ×16, but **zero** occurrences of `"Sheriff Patrol"`. Without
normalisation the check fails all nine every run, and a check that cannot
pass is a check people learn to ignore.

Rule: when an entity's `display:` carries a `(variant X)` or `(variant Y)`
suffix, strip the suffix **and** strip any leading `Sheriff ` (case-sensitive,
English title-case only — `"sheriff_"` lowercase is the registry slug, not
the display prefix). The remaining archetype token is the search term.

Applied to the registry entry `sheriff_patrol_a` with `display: "Sheriff Patrol (variant A)"`:

```
display            = "Sheriff Patrol (variant A)"
display_no_variant = "Sheriff Patrol"
display_archetype  = "Patrol"
search_tokens      = ["Patrol"]      # "Sheriff Patrol" is also tried but expected to miss
```

So for each entity, build:

```
search_tokens[0] = display_archetype   # always tried first
search_tokens[1] = display_no_variant  # tried second if [0] misses
search_tokens[2] = display             # tried third if [1] misses
entity_name      = always tried as a fallback
```

A hit on **any** of the four tokens in the source GDD counts as a successful
source-mention match. The first hit's context lines are used for value
extraction.

For each entity:

```
Grep pattern="[search_token_0]|[search_token_1]|[search_token_2]|[entity_name]" glob="design/gdd/*.md" output_mode="content" -C 3
```

When multiple tokens match, prefer the most specific (lower index). When
`search_token_0` (the archetype) hits, treat that as the canonical match and
ignore any spurious hits from later tokens.

For each GDD hit, extract the values mentioned near the matched token:
- any numeric attributes (counts, costs, durations, ranges, rates)
- any categorical attributes (types, tiers, categories)
- any derived values (totals, outputs, results)
- any other attributes registered in entity_map

Compare extracted values against the registry entry.

**Conflict detection:**
- Registry says `[entity_name].[attribute] = [value_A]`. GDD says `[entity_name] has [value_B]`. → **CONFLICT**
- Registry says `[item_name].[attribute] = [value_A]`. GDD says `[item_name] is [value_B]`. → **CONFLICT**
- GDD mentions `[entity_name]` (or any of its normalised tokens) but doesn't specify the attribute. → **NOTE** (no conflict, just unverifiable)
- **Source-mention miss**: **none** of the four tokens occur in the claimed `source:` file. → **SOURCE-MENTION MISS** (a separate signal — the entity is registered against a GDD that doesn't name it; not a CONFLICT but worth flagging). Distinguish from `NOTE`: `NOTE` says the entity is mentioned but its attributes aren't stated; `SOURCE-MENTION MISS` says it isn't mentioned at all.

### 3b: Item Scan

For each item in item_map, grep all GDDs for the item name. Extract:
- sell price / value / gold value
- weight
- stack rules (stackable / non-stackable)
- category

Compare against registry entry values.

### 3c: Formula Scan

For each formula in formula_map, grep all GDDs for the formula name. Extract:
- variable names mentioned near the formula
- output range or cap values mentioned

Compare against registry entry:
- Different variable names → **CONFLICT**
- Output range stated differently → **CONFLICT**

### 3d: Constant Scan

For each constant in constant_map, grep all GDDs for the constant name. Extract:
- Any numeric value mentioned near the constant name

Compare against registry value:
- Different number → **CONFLICT**

---

## Phase 4: Deep Investigation (Conflicts Only)

For each conflict found in Phase 3, do a targeted full-section read of the
conflicting GDD to get precise context:

```
Read path="design/gdd/[conflicting_gdd].md"
```
(Or use Grep with wider context if the file is large)

Confirm the conflict with full context. Determine:
1. **Which GDD is correct?** Check the `source:` field in the registry — the
   source GDD is the authoritative owner. Any other GDD that contradicts it
   is the one that needs updating.
2. **Is the registry itself out of date?** If the source GDD was updated after
   the registry entry was written (check git log), the registry may be stale.
3. **Is this a genuine design change?** If the conflict represents an intentional
   design decision, the resolution is: update the source GDD, update the registry,
   then fix all other GDDs.

For each conflict, classify:
- **🔴 CONFLICT** — same named entity/item/formula/constant with different values
  in different GDDs. Must resolve before architecture begins.
- **⚠️ STALE REGISTRY** — source GDD value changed but registry not updated.
  Registry needs updating; other GDDs may be correct already.
- **ℹ️ UNVERIFIABLE** — entity mentioned but no comparable attribute stated.
  Not a conflict; just noting the reference.

---

## Phase 5: Output Report

```
## Consistency Check Report
Date: [date]
Registry entries checked: [N entities, N items, N formulas, N constants]
GDDs scanned: [N] ([list names])

---

### Conflicts Found (must resolve before architecture)

🔴 [Entity/Item/Formula/Constant Name]
   Registry (source: [gdd]): [attribute] = [value]
   Conflict in [other_gdd].md: [attribute] = [different_value]
   → Resolution needed: [which doc to change and to what]

---

### Stale Registry Entries (registry behind the GDD)

⚠️ [Entry Name]
   Registry says: [value] (written [date])
   Source GDD now says: [new value]
   → Update registry entry to match source GDD, then check referenced_by docs.

---

### Unverifiable References (no conflict, informational)

ℹ️ [gdd].md mentions [entity_name] but states no comparable attributes.
   No conflict detected. No action required.

---

### Clean Entries (no issues found)

✅ [N] registry entries verified across all GDDs with no conflicts.

---

Verdict: PASS | CONFLICTS FOUND
```

**Verdict:**
- **PASS** — no conflicts. Registry and GDDs agree on all checked values.
- **CONFLICTS FOUND** — one or more conflicts detected. List resolution steps.

---

## Phase 6: Registry Corrections

If stale registry entries were found, ask:
> "May I update `design/registry/entities.yaml` to fix the [N] stale entries?"

For each stale entry:
- Update the `value` / attribute field
- Set `revised:` to today's date
- Add a YAML comment with the old value: `# was: [old_value] before [date]`

If new entries were found in GDDs that are not in the registry, ask:
> "Found [N] entities/items mentioned in GDDs that aren't in the registry yet.
> May I add them to `design/registry/entities.yaml`?"

Only add entries that appear in more than one GDD (true cross-system facts).

**Never delete registry entries.** Set `status: deprecated` if an entry is removed
from all GDDs.

After writing: Verdict: **COMPLETE** — consistency check finished.
If conflicts remain unresolved: Verdict: **BLOCKED** — [N] conflicts need manual resolution before architecture begins.

### 6b: Append to Reflexion Log

If any 🔴 CONFLICT entries were found (regardless of whether they were resolved),
append an entry to `docs/consistency-failures.md` for each conflict:

```markdown
### [YYYY-MM-DD] — /consistency-check — 🔴 CONFLICT
**Domain**: [system domain(s) involved]
**Documents involved**: [source GDD] vs [conflicting GDD]
**What happened**: [specific conflict — entity name, attribute, differing values]
**Resolution**: [how it was fixed, or "Unresolved — manual action needed"]
**Pattern**: [generalised lesson, e.g. "Item values defined in combat GDD were not
referenced in economy GDD before authoring — always check entities.yaml first"]
```

If `docs/consistency-failures.md` does not exist, create it with this header before appending:

```markdown
# Consistency Failure Log

<!-- Auto-maintained by /consistency-check. Do not edit manually. -->
<!-- One entry per detected conflict, in chronological order. -->

| Date | GDD A | GDD B | Conflict Type | Status |
|------|-------|-------|---------------|--------|
```

Then append the new conflict entries. Never skip logging — a missing file is not a reason to lose conflict history.

---

## Phase 7: Session State and Closing

Silently append to `production/session-state/active.md` (create the file if it does not exist):

```
<!-- CONSISTENCY-CHECK: [date] | GDDs checked: [N] | Conflicts found: [N] | Report: docs/consistency-report-[date].md -->
```

Then close with an `ask the user (see docs/vendor-map.md)` widget:

- **Prompt**: "Consistency check complete — [N] conflicts found. What next?"
- **Options**:
  - `[A] Fix the highest-priority conflict now`
  - `[B] Save full report and stop`
  - `[C] Run /design-review on the most conflicted GDD`
  - `[D] Stop here`

Never end the skill with plain text. Always close with this widget.

---

## Recovery / Reference

- **If PASS**: Run `/review-all-gdds` for holistic design-theory review, or
  `/create-architecture` if all MVP GDDs are complete.
- **If CONFLICTS FOUND**: Fix the flagged GDDs, then re-run
  `/consistency-check` to confirm resolution.
- **If STALE REGISTRY**: Update the registry (Phase 6), then re-run to verify.
- Run `/consistency-check` after writing each new GDD to catch issues early,
  not at architecture time.

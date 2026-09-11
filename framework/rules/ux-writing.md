paths:
  - "assets/data/strings/**"
  - "design/ux/**"
  - "design/narrative/**"
  - "assets/Scripts/UI/**"
---

# UX Writing Rules (USER directive, 2026-09-05)

Binding for every on-screen instruction, tutorial, UI label, subtitle, action
line and narration line — in the string tables, the UX specs that author copy,
the narrative files, and any C# that composes player-facing text.

0. Write as an expert game writer specialising in hyper-accessible UX writing
   and mobile microcopy.
1. **Audience**: global, including non-native English speakers, children and
   casual players. Aim for a 3rd to 4th-grade reading level.
2. **Direct action first**: every instructional sentence starts with an active
   verb. "Tap the seal to pay." Never "If you want to pay, the seal can be
   tapped."
3. **One idea per sentence**: do not chain actions with commas. Split them.
4. **Kill the fluff**: no filler words, lore jargon or flavour text inside a
   mechanical instruction. Narration stays punchy.
5. **Standard terminology**: mobile gestures only — Tap, Swipe, Drag, Hold.
   Never Click or Press.
6. **Scannability**: lists as bullet points; bold the exact target name or
   action — "Tap **Record the alms** to pay."

## How this meets the existing voice

- Mechanical copy (subtitles, action lines, button labels, the first-run
  framing, tutorial text, error text) follows all six rules with no exception.
- The Ledger's grim-satire register (`design/narrative/tone-guide.md`, the
  situation narratives) is narration, so rule 4's "punchy" and rule 1's
  reading level apply to it too. Existing approved entries that exceed the
  reading level were audited under TASK #0896. USER 2026-09-05: the 33 prose
  entries are tightened to the rule (TASK #0899); the 22 Ascendant-band ballad
  stanzas keep their verse form — a documented voice exemption, the only one.
  New prose entries are written to the rule from now on.
- IP rules (`docs/legal/IP-COMPLIANCE.md`) and the `pd_source` registry still
  bind every named entity; this rule changes how copy reads, not what it may
  name.

## Checks

- A string-table key that starts an instruction with anything but a verb is a
  defect.
- "Press", "Click", "Select" in a player-facing string is a defect.
- Any sentence over ~15 words in a mechanical instruction gets split.

---
paths:
  - "assets/Scripts/M1/**"
---

# Engine-Coupled Runtime Rules

Scope: `assets/Scripts/M1/**` — the Unity runtime layer (scene glue, bootstraps, controllers,
beat timing); `assets/Scripts/UI/**` is `.claude/rules/ui-code.md`. A new top-level area under
`assets/Scripts/` needs a `technical-director` scope decision first.
`assets/Scripts/Sim/` is a gitignored junction to `src/Greenwood.Sim/` — never develop there.
The Unity root is lowercase `assets/` (`.claude/rules/case-sensitivity.md`).
Owners: `unity-specialist`, `gameplay-programmer`.

## Layering

- **Presentation depends on the sim; never the reverse.** Cross-boundary needs implement a
  sim-owned interface (`IRng`, `IBeatLog`, `ISaveSerializer`, `IBandPersister`).
- **No game logic here.** A method that decides an outcome, computes a formula or consumes
  randomness belongs in `src/Greenwood.Sim/**`; this layer only presents.
- **No `Find`, `FindObjectOfType` or gameplay singletons.** Use `[SerializeField]` scene
  references or bootstrap injection.

## Engine API discipline

- **Training data predates the pinned engine.** Look every Unity API up in
  `docs/engine-reference/unity/` (`VERSION.md` = pinned version + Pixel Perfect Camera
  settings).
- Registry packages only, via `Packages/manifest.json`. No dropped `.dll`/`.unitypackage`; a
  new dependency needs an ADR.
- Do **not** add `com.unity.2d.pixel-perfect` (`PixelPerfectCamera` is in URP 17 at
  `UnityEngine.Rendering.Universal`) or `com.unity.textmeshpro` (TMP is in `com.unity.ugui`
  2.5.0). No `com.unity.inputsystem` — legacy input only.
- UI is UGUI + TMP, not UI Toolkit (ADR-027). JSON is `Newtonsoft.Json` with ADR-026's custom
  `ContractResolver`, never `System.Text.Json`. Tests: `.claude/rules/unity-testing.md`.
  Scene-path compares use `StringComparison.OrdinalIgnoreCase`.
- A changed engine fact updates `VERSION.md` and the control manifest in the same PR.

## Performance

Budget (`.claude/docs/technical-preferences.md`): 60 fps, 16.6 ms frame, <=120 draw calls,
<=400 MB (2021 mid-range Android).

- **Zero allocations in per-frame paths** (`Update`, `LateUpdate`, per-frame coroutines):
  pre-allocate, pool, reuse. A `new` inside `Update` is a defect.
- **Profile before and after every optimisation; record the numbers** in the task/ADR.
- Time with `Time.deltaTime`; durations come from `assets/data/tuning.json`, never a literal.
- Never block the main thread: long work is a coroutine or moves off the frame.

## Documentation, YAML assets, regressions

- Every public type and member carries a `///` doc comment. Cite the ADR or GDD section a
  controller implements; verify the citation resolves (`.claude/rules/architecture-docs.md`).
- **Never put `#` comments in `.mixer`, `.unity`, `.prefab`, `.asset` or `.meta`.** That YAML
  *subset* can fail to deserialise, and Unity strips comments on re-save. Explain in the
  consuming C# or the directory README.
- Diff failing test **ids** against the `results.xml` baseline, not totals.

Background: docs/engineering-notes/engine-code.md

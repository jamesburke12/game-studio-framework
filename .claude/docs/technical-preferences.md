# Technical Preferences

## Engine & Language
- **Engine**: Unity 6 (6000.x LTS)
- **Language**: C# (latest supported by the Unity version)
- **Rendering**: URP 2D Renderer
- **Physics**: none in the sim. Unity 2D physics only for incidental presentation.
- **Pixel pipeline**: Pixel Perfect Camera at PPU 16 — ships **inside URP 17**
  (`UnityEngine.Rendering.Universal`). **Do not add `com.unity.2d.pixel-perfect`** —
  obsolete on Unity 6 and it breaks the build (TASK #0378, 2026-08-23)
- **UI**: `com.unity.ugui` 2.5.0 — UGUI + TextMeshPro on Screen Space–Overlay
  (ADR-027). TMP ships inside that package; do not add `com.unity.textmeshpro`

## Input & Platform
- **Target Platforms**: Android (API 26+), iOS 15+
- **Input Methods**: Touch only
- **Primary Input**: Single-thumb touch, portrait
- **Gamepad Support**: None
- **Touch Support**: Full
- **Orientation**: Portrait-primary, live rotation to landscape. See `design/ux/orientation-and-layout.md`.
- **Platform Notes**: Touch targets ≥44 logical px. Must hold 60fps on a 2021 mid-range Android.

## Naming Conventions
- **Classes**: `PascalCase`
- **Methods**: `PascalCase`
- **Private fields**: `_camelCase`
- **Locals / parameters**: `camelCase`
- **Constants**: `PascalCase` (not SCREAMING_CASE)
- **Interfaces**: `IPascalCase`
- **Files**: match the primary type name exactly
- **Prefabs**: `PascalCase.prefab`
- **ScriptableObjects**: `SO_PascalCase`
- **Data JSON**: `kebab-case.json`
- **Assemblies**: `<Project>.<Area>`

## Assemblies
| Assembly | Unity refs? | Contains |
|---|---|---|
| `<Project>.Sim` | ❌ **never** | All game logic. netstandard2.1. |
| `<Project>.Data` | minimal | Content schemas, ScriptableObjects, JSON loading |
| `<Project>.Game` | yes | Views, input, presentation, scene glue |
| `<Project>.Sim.Tests` | ❌ | NUnit against the sim |

## Performance Budgets
- **Target Framerate**: 60 fps
- **Frame Budget**: 16.6 ms
- **Draw Calls**: ≤120
- **Memory Ceiling**: 400 MB
- **APK/IPA size**: ≤150 MB
- **Total audio**: ≤22 MB
- **Counterfactual re-run**: <50 ms for 8 candidates on mid-range hardware

## Testing
- **Framework**: NUnit via `dotnet test` for `<Project>.Sim`; Unity Test Framework for engine-coupled tests
- **Minimum Coverage**: 80% on `<Project>.Sim`
- **Required Tests**: every formula in every GDD §4, synergy evaluation, determinism (same seed → identical beat log), save/resume

## Forbidden Patterns
- `using UnityEngine` anywhere in `<Project>.Sim` — **CI failure**
- Hardcoded gameplay values in C# — all tuning lives in `assets/data/tuning.json`
- `Random` seeded from wall-clock anywhere
- `Find`, `FindObjectOfType`, or singletons for gameplay wiring — inject instead
- Anti-aliasing, bilinear filtering, or non-integer sprite scaling
- Off-palette pixels in `assets/art/` — **CI failure**
- Any asset committed without a provenance JSON — **CI failure**
- Cross-fading between the Field and Ledger registers

## Allowed Libraries
- Unity Registry packages only, declared in `Packages/manifest.json`
- No manually dropped `.dll` or `.unitypackage`
- Any new dependency needs an ADR

## Architecture Decisions Log
- [ADR-001](../../docs/architecture/ADR-001-deterministic-sim.md) — Engine-independent deterministic simulation (Accepted)

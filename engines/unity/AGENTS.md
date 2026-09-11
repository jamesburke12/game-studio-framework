# Unity overlay — engine instructions

Install with `python tools/framework/install.py --engine unity`. It writes `framework/engine.txt`, copies these workflows into `.github/workflows/`, the `unity-mobile` profile into `framework/profiles/`, and syncs the four Unity rules (`engine-code`, `unity-testing`, `case-sensitivity`, `ui-code`) alongside the generic ones. A project's `AGENTS.md` imports this file after the studio instructions.

## Technology stack (fill the pins in `docs/engine-reference/unity/VERSION.md`)

- **Editor binary (Windows)**: `C:\Program Files\Unity\Hub\Editor\<version>\Editor\Unity.exe` — quote it, it has spaces; `unity` on PATH should be the **Unity CLI** (`%LOCALAPPDATA%\Unity\bin\unity.exe`), never the editor. Headless editor runs need `-batchmode -nographics -quit -projectPath . -executeMethod <Class.Method> -logFile -`; without `-logFile -` you get an exit code and nothing else.
- **Packages**: UPM manifest only. No hand-dropped .dll or .unitypackage. Version traps for the pinned editor go in `VERSION.md`, one bullet each, with the date and the run that proved them.
- **Tests**: Unity Test Framework (NUnit 4 constraint model) for engine-coupled tests; `dotnet test` for the engine-independent simulation.
- **UI**: pick one UI stack in an ADR and name it here (UGUI + TextMeshPro, or UI Toolkit). Never both.
- **Pixel pipeline / render pipeline**: name the pipeline and the camera settings here once they are decided; the settings live in `VERSION.md`, everything else links to it.

### The simulation is engine-independent

`src/<Project>.Sim/` is a **pure C# library with zero Unity references**, owning all game logic: resolution, synergies, economy, seeded RNG. Unity only presents it, and `dotnet build src/<Project>.Sim` must succeed with Unity absent. **Never** add a `UnityEngine` using-directive — a system needing one is in the wrong assembly.

## Gates

- **Workers never run Unity.** A fresh worktree has no `Library/`, and one batchmode run at a time is the machine's ceiling. Workers run `dotnet test`, open the PR and label it `gate:queued`.
- **The Unity gate is `unity-gate.yml`** on a self-hosted runner: `unity test --mode EditMode` then `--mode PlayMode` through the Unity CLI (`--format github`, JUnit report), compared against the daily `gate-baseline.yml` artifact so pre-existing failures never block a PR. It runs on `workflow_dispatch` with a PR number; `unity-gate-queue.yml` turns the `gate:queued` label into that dispatch, and the gate's last step dispatches the next queued PR.
- **Exit codes**: `unity test --format github` exits 2 on test failures, 8 with `--format json`, 6 when no verdict was produced (compile, licence, crash, timeout).
- **Repository variables** the workflows read: `UNITY_CLI` (path to the CLI binary on the runner), `UNITY_GATE_FILTER` (optional NUnit filter to exclude nightly-only fixtures), `SIM_PROJECT`, `SIM_TESTS_PROJECT`.
- **Memory**: a resident editor is 2–4 GB. Two Unity processes are the hard ceiling on one machine: the gate plus the lead's interactive editor, never a third.

## Case-sensitivity

Windows folds case and git does not. The canonical asset root is lowercase `assets/`; every path in scripts, asmdefs and docs is written lowercase, and string comparisons against Unity paths use `StringComparison.OrdinalIgnoreCase`. Detail: `engines/unity/rules/case-sensitivity.md`.

## Roles

Unity engine work routes to `unity-specialist`; UGUI / UI Toolkit implementation to `unity-ui-specialist` or `ui-programmer`; shaders and the pixel pipeline to `technical-artist`.

paths:
  - "Assets/**"
  - "assets/**"
---

# Case-Sensitivity Discipline

Windows is case-insensitive and case-preserving; git's index is case-sensitive; `git mv` keeps
the original path's case. So one physical file can end up tracked twice — once as `Assets/...`,
once as `assets/...`. The canonical root in this repo is lowercase `assets/`.

Symptoms: files clearly present on disk show as untracked; `git ls-files | grep -i <name>`
returns two entries; `git log --all -- <path>` shows history for a path `git status` calls
untracked.

## Detection — before declaring any sprint closed

```bash
git ls-files | grep -E "^Assets/" | wc -l   # must be 0 (lowercase is canonical here)
git ls-files | grep -E "^assets/" | wc -l   # the canonical count
git status --short | wc -l                  # 0: nothing untracked, nothing modified
git ls-files | grep -i <recently-moved-file> # exactly 1 entry per physical file
```

Any non-zero first count, or any doubled entry, is the defect. Fix it before the sprint is
declared done, or document the divergence.

## Fix

1. Confirm the canonical case on disk (`ls`), not from git.
2. `git rm --cached <WrongCase/path> …` — drops the index entry, keeps the file.
3. `git add assets/` — picks up the canonical paths' `.meta` and other untracked files.
4. Re-run the detection commands; non-`.meta` untracked files still need handling separately.
5. Commit as part of the sprint close: "Reconcile working tree".

## Prevention when moving directories

- Always write lowercase `assets/...` in paths, scripts, asmdefs and docs.
- Rename through a temporary path so the case change is a real rename to git:
  ```bash
  git mv old/path temp_path_$$
  git mv temp_path_$$ New/Path
  ```
- Verify straight after: `git ls-files | grep -i <filepath>` returns exactly 1 entry.
- `git config core.ignorecase false` helps git only; the filesystem still folds case.

## In-code variant — compare Unity paths case-insensitively

`EditorBuildSettings.scenes` and `EditorSceneManager.OpenScene` normalise stored paths to
`"Assets/..."` (capital A). C# `==` is case-sensitive, so a lowercase literal misses an existing
entry and the scene is added twice, or an open silently fails.

```csharp
if (s.path.Equals(scenePath, StringComparison.OrdinalIgnoreCase)) { … }   // required
```

Detection — any hit here is suspicious, and `tools/ci/validate-case-sensitivity.py` gates it:

```bash
grep -rnE '"[Aa]ssets/' Assets/Scripts/Editor/ | grep -E '==|\.Equals\(' | head
```

Every `string` comparison against a Unity path uses `StringComparison.OrdinalIgnoreCase`.

Background: docs/engineering-notes/case-sensitivity.md

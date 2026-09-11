#!/usr/bin/env python3
"""
Validate that authored docs stay under their size caps.

Large docs load into every session, subagent and compaction — the same cost
class as TODO.md (see CLAUDE.md's task-tracking section). This checks a fixed
set of doc families against byte caps and flags any tracked *.log under
production/.

Modes:
  --warn (default) — print every violation, exit 0.
  --strict          — print every violation, exit 1 if any found.

Exit codes:
  0 — no violations, or --warn mode
  1 — violations found in --strict mode
  2 — script error
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-16"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf-16"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()

SKIP_DIRS = ("design/gdd/_history/", "docs/architecture/notes/", "production/sprints/_closed/")

# (glob, cap_bytes, group)
CAPS = [
    ("design/gdd/*.md", 25600, "GDD"),
    ("docs/architecture/ADR-*.md", 8192, "ADR"),
    ("production/epics/**/story-*.md", 8192, "story"),
    ("production/stories/*.md", 8192, "story"),
    ("production/sprints/sprint-*.md", 20480, "sprint plan"),
    ("docs/architecture/control-manifest.md", 10240, "manifest"),
    ("docs/architecture/**/*.yaml", 30720, "yaml"),
    ("production/**/*.yaml", 30720, "yaml"),
]

CLOSED_STATUSES = {"complete", "done", "superseded"}
STATUS_RE = re.compile(r"^\**\s*Status\**\s*:\**\s*(.+?)\s*$", re.IGNORECASE)
SPRINT_RE = re.compile(r"^sprint:\s*(\S+)", re.MULTILINE)


def _story_is_open(path):
    """Read a story's Status header; treat missing status as open."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True
    for line in text.splitlines()[:20]:
        m = STATUS_RE.match(line.strip().lstrip("> ").strip())
        if m:
            return m.group(1).strip().lower() not in CLOSED_STATUSES
    return True


def _active_sprint():
    yaml_path = REPO_ROOT / "production" / "sprint-status.yaml"
    try:
        text = yaml_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = SPRINT_RE.search(text)
    return m.group(1) if m else None


def _skip(rel_path):
    posix = rel_path.as_posix()
    return any(posix.startswith(d) for d in SKIP_DIRS)


def _tracked_files():
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return {line.strip() for line in out.stdout.splitlines() if line.strip()}


def find_violations():
    violations = []
    tracked = _tracked_files()
    seen = set()
    active_sprint = _active_sprint()

    for pattern, cap, group in CAPS:
        is_story_glob = pattern in (
            "production/epics/**/story-*.md",
            "production/stories/*.md",
        )
        is_sprint_glob = pattern == "production/sprints/sprint-*.md"
        for path in REPO_ROOT.glob(pattern):
            if not path.is_file():
                continue
            rel = path.relative_to(REPO_ROOT)
            if _skip(rel):
                continue
            posix = rel.as_posix()
            if posix not in tracked:
                continue
            if is_story_glob and not _story_is_open(path):
                continue
            if is_sprint_glob and active_sprint is not None:
                if path.stem != f"sprint-{active_sprint}":
                    continue
            key = (posix, cap)
            if key in seen:
                continue
            seen.add(key)
            size = path.stat().st_size
            if size > cap:
                violations.append((posix, size, cap, group))

    for posix in tracked:
        if posix.startswith("production/") and posix.endswith(".log"):
            violations.append((posix, None, "no .log tracked under production/", "log"))

    violations.sort(key=lambda v: v[0])
    return violations


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--warn", action="store_true")
    args = parser.parse_args()
    strict = args.strict and not args.warn

    try:
        violations = find_violations()
    except subprocess.CalledProcessError as exc:
        print(f"error: git ls-files failed: {exc}", file=sys.stderr)
        return 2

    for posix, size, cap, _group in violations:
        if size is None:
            print(f"{posix}: {cap}")
        else:
            print(f"{posix}: {size} bytes (cap {cap})")

    counts = {}
    for _posix, _size, _cap, group in violations:
        counts[group] = counts.get(group, 0) + 1

    print("--- summary ---")
    for group in ("GDD", "ADR", "story", "sprint plan", "manifest", "yaml", "log"):
        print(f"{group}: {counts.get(group, 0)}")
    print(f"total: {len(violations)} violation(s)")

    if strict and violations:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

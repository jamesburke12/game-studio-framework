#!/usr/bin/env python3
"""
Validate that lead-only files (per CLAUDE.md) are not touched by non-lead
commits in git history.

Per CLAUDE.md "sprint-status.yaml is lead-only via /dev-story and /story-done
— never hand-edited". The discipline: certain files are owned by the lead
role. Subagent commits should not modify them. This script scans git history
for commits that touched any of the lead-only paths, and flags commits
whose author email is not the lead's.

Lead-only files (as of 2026-08-26):
  - production/sprint-status.yaml
  - production/retrospectives/   (whole directory)
  - docs/registry/architecture.yaml
  - docs/registry/tr-registry.yaml
  - design/registry/entities.yaml
  - production/stage.txt
  - production/review-mode.txt

Lead identification: by commit author email. The lead's email is read from
`.github/agent-routing.yaml` (`lead.email`); the `LEAD_EMAIL` environment
variable overrides it. Subagent commits show as a different author, so any
commit on a lead-only path whose author email != lead is flagged.

Exit codes: 0 no violations · 1 violations found · 2 tooling error
"""

import os
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent.parent.resolve()

# Lead-only paths (repo-relative globs).
LEAD_ONLY_PATTERNS = [
    "production/sprint-status.yaml",
    "production/retrospectives/",
    "docs/registry/architecture.yaml",
    "docs/registry/tr-registry.yaml",
    "design/registry/entities.yaml",
    "production/stage.txt",
    "production/review-mode.txt",
]

ROUTING_YAML = REPO_ROOT / ".github" / "agent-routing.yaml"


def lead_email() -> str:
    """LEAD_EMAIL env var, else `lead.email` from .github/agent-routing.yaml."""
    email = os.environ.get("LEAD_EMAIL", "").strip()
    if email:
        return email
    if not ROUTING_YAML.is_file():
        raise ValueError(f"{ROUTING_YAML} does not exist and LEAD_EMAIL is unset")
    text = ROUTING_YAML.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text) or {}
        email = str((data.get("lead") or {}).get("email") or "").strip()
    except ImportError:
        # Minimal fallback: the `email:` line inside the top-level `lead:` block.
        in_lead = False
        for line in text.splitlines():
            stripped = line.split("#", 1)[0].rstrip()
            if not stripped:
                continue
            if not line[0].isspace():
                in_lead = stripped.startswith("lead:")
                continue
            if in_lead and stripped.strip().startswith("email:"):
                email = stripped.split(":", 1)[1].strip().strip("'\"")
                break
    if not email:
        raise ValueError("lead.email is missing from .github/agent-routing.yaml (or set LEAD_EMAIL)")
    return email


# The lead is identified by commit author email: headless workers and the
# gate runner commit as the same account under other display names.
def lead_author_pattern() -> re.Pattern[str]:
    return re.compile("<" + re.escape(lead_email()) + ">", re.IGNORECASE)

# How many recent commits to scan. Bounded so the script runs quickly in CI.
SCAN_LIMIT = 200


def git_log_lead_only() -> list[tuple[str, str, list[str]]]:
    """
    Run `git log --name-only` against HEAD and return a list of
    (commit_hash, author_line, [file_paths]) for every commit that touched
    a lead-only path within the last SCAN_LIMIT commits.
    """
    cmd = [
        "git", "log", f"-n{SCAN_LIMIT}",
        "--pretty=format:%H %an <%ae>",
        "--name-only",
    ]
    result = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        print(f"ERROR: git log failed: {result.stderr}", file=sys.stderr)
        return []

    commits: list[tuple[str, str, list[str]]] = []
    current_hash = None
    current_author = None
    current_files: list[str] = []

    for line in result.stdout.splitlines():
        line = line.rstrip()
        if not line:
            continue
        # Author line: "<hash> <name> <email>"
        if re.match(r"^[0-9a-f]{40}\s+", line):
            if current_hash and current_files:
                commits.append((current_hash, current_author, current_files))
            parts = line.split(maxsplit=1)
            current_hash = parts[0]
            current_author = parts[1] if len(parts) > 1 else ""
            current_files = []
        else:
            # File path line
            if any(line.startswith(p) or p.startswith(line + "/") for p in LEAD_ONLY_PATTERNS):
                current_files.append(line)

    if current_hash and current_files:
        commits.append((current_hash, current_author, current_files))

    return commits


def is_lead_only_path(path: str) -> bool:
    """True if path matches any lead-only pattern."""
    for p in LEAD_ONLY_PATTERNS:
        if path == p or path.startswith(p):
            return True
    return False


def main() -> int:
    try:
        pattern = lead_author_pattern()
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    commits = git_log_lead_only()
    if not commits:
        print("ERROR: git log produced no lead-only commits (git failure)", file=sys.stderr)
        return 2

    violations: list[tuple[str, str, list[str]]] = []
    for commit_hash, author, files in commits:
        if pattern.search(author):
            continue
        # Non-lead author touched a lead-only file.
        violations.append((commit_hash, author, files))

    if not violations:
        print(f"OK — scanned {len(commits)} recent commits; all lead-only-file authors are the lead.")
        return 0

    print(f"FAIL: {len(violations)} non-lead commit(s) touched lead-only files:")
    for commit_hash, author, files in violations:
        short = commit_hash[:7]
        print(f"  {short} by '{author}':")
        for f in files:
            print(f"    {f}")
        print()
    print("Per CLAUDE.md, lead-only files are owned by the lead role. Subagent")
    print("commits that need to update a lead-only file should request the")
    print("lead to do it (or escalate to /sprint-plan / /story-done for the")
    print("canonical update paths).")
    return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Orca dispatch loop — one pass per invocation. A scheduler or the lead reruns it.

Reads the ready-issue queue, picks a routing row + vendor per issue, batches
up to 4 compatible issues, and launches a worker via `orca orchestration
worker-start` (falling back to `orca worktree create`). Default is --dry-run:
prints decisions and the brief head, launches nothing, edits no labels.

See tools/orca/README.md for flags and the brief template.
"""

import sys
import os
import json
import argparse
import subprocess
import re
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
ROUTING_YAML = ROOT / ".github" / "agent-routing.yaml"
LOG_PATH = ROOT / "tools" / "orca" / "dispatch-log.md"
REVIEW_LOGS_DIR = ROOT / "tools" / "orca" / "logs"
BRIEFS_DIR = Path(os.environ.get("ORCA_BRIEFS_DIR", Path.home() / "orca" / "briefs"))
BATCH_SIZE = 4
REVIEWER_TIMEOUT_S = 900
INSTALL_SCRIPT = ROOT / "tools" / "framework" / "install.py"
PROFILES_DIR = ROOT / "framework" / "profiles"
DEFAULT_PROFILE = "unity-mobile"


def resolve_profile(role):
    """Worker profile: the role's own yaml if one exists, else the default."""
    if role and (PROFILES_DIR / f"{role}.yaml").is_file():
        return role
    return DEFAULT_PROFILE


def install_cmd(profile):
    return [sys.executable, str(INSTALL_SCRIPT), "--profile", profile]


def apply_profile(wt_path, profile, dry_run):
    cmd = install_cmd(profile)
    if dry_run:
        print(f"  install cmd: {cmd}")
        return
    if not wt_path or not Path(wt_path).exists():
        print(f"# profile install skipped: no usable worktree path ({wt_path!r})")
        return
    try:
        subprocess.run(cmd, cwd=wt_path, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        _fail_detail(cmd, e)


def load_routing():
    import yaml
    with open(ROUTING_YAML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _fail_detail(cmd, e):
    detail = (getattr(e, "stderr", "") or getattr(e, "stdout", "") or "").strip()[:400]
    print(f"# command failed: {' '.join(cmd)}")
    print(f"#   {detail}")


def run_gh(args, json_out=True):
    cmd = ["gh"] + args
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=ROOT)
    except subprocess.CalledProcessError as e:
        _fail_detail(cmd, e)
        return [] if json_out else ""
    if json_out:
        try:
            return json.loads(out.stdout)
        except json.JSONDecodeError:
            return []
    return out.stdout


def run_orca(args):
    cmd = ["orca"] + args
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=ROOT)
        return True, out.stdout
    except subprocess.CalledProcessError as e:
        _fail_detail(cmd, e)
        return False, (e.stdout or "") + (e.stderr or "")


def milestone_key(issue):
    ms = issue.get("milestones") or issue.get("milestone")
    title = ""
    if isinstance(ms, dict):
        title = ms.get("title", "")
    elif isinstance(ms, list) and ms:
        title = ms[0].get("title", "")
    m = re.search(r"Sprint\s+(\d+)", title or "")
    return (int(m.group(1)) if m else 9999, title or "")


def label_names(issue):
    return {l["name"] for l in issue.get("labels", [])}


def role_from_labels(labels):
    for l in labels:
        if l.startswith("role:"):
            return l.split(":", 1)[1]
    return None


def stage_from_labels(labels):
    for l in labels:
        if l.startswith("stage:"):
            return l.split(":", 1)[1]
    return None


def vendor_from_labels(labels):
    """`vendor:any` means no restriction; `vendor:claude`/`vendor:codex`
    restrict to that vendor."""
    vendors = {l.split(":", 1)[1] for l in labels if l.startswith("vendor:")}
    return vendors - {"any"}


def is_blocked(issue_number, owner_repo):
    ok, out = run_gh_raw(
        ["api", f"repos/{owner_repo}/issues/{issue_number}/dependencies/blocked_by"]
    )
    if not ok:
        return False
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return False
    if not isinstance(data, list):
        return False
    for b in data:
        if b.get("state") == "open":
            return True
    return False


def run_gh_raw(args):
    cmd = ["gh"] + args
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=ROOT)
        return True, out.stdout
    except subprocess.CalledProcessError as e:
        _fail_detail(cmd, e)
        return False, e.stderr


def get_owner_repo():
    out = run_gh(["repo", "view", "--json", "nameWithOwner"])
    if isinstance(out, dict):
        return out.get("nameWithOwner")
    return None


def match_row(routing, role, stage):
    for row in routing.get("rows", []):
        match = row.get("match", {})
        if "roles" in match and role in match["roles"]:
            return row
        if "stage" in match and match["stage"] == stage:
            return row
    return None


def vendor_available(vendor, model_entry, capacity, cooldown, running_counts):
    cap = capacity.get(vendor)
    if cap is None:
        return False
    if running_counts.get(vendor, 0) >= cap:
        return False
    cd = cooldown.get(vendor)
    if cd:
        try:
            cd_time = datetime.fromisoformat(cd.replace("Z", "+00:00"))
            if cd_time > datetime.now(timezone.utc):
                return False
        except ValueError:
            pass
    return True


def running_worker_counts():
    ok, out = run_orca(["orchestration", "worker-list", "--json"])
    counts = {}
    if ok:
        try:
            data = json.loads(out)
            workers = data if isinstance(data, list) else data.get("workers", [])
            for w in workers:
                v = w.get("agent") or w.get("vendor")
                if v:
                    counts[v] = counts.get(v, 0) + 1
            # Antigravity workers are plain terminals Orca does not list as
            # workers; the dispatcher leaves a `vendor` marker beside the brief
            # and the worktree existing means the worker is still live.
            live_names = {(w.get("displayName") or w.get("name") or "") for w in list_worktrees()}
            for marker in BRIEFS_DIR.glob("issue-*/vendor"):
                if marker.parent.name in live_names and marker.read_text(encoding="utf-8").strip() == "antigravity":
                    counts["antigravity"] = counts.get("antigravity", 0) + 1
            return counts
        except (json.JSONDecodeError, AttributeError):
            pass
    # Fallback: count issues labelled status:in-progress with vendor:<v>
    issues = run_gh(
        ["issue", "list", "-l", "status:in-progress", "--state", "open",
         "--limit", "200", "--json", "labels"]
    )
    for issue in issues if isinstance(issues, list) else []:
        for l in label_names(issue):
            if l.startswith("vendor:"):
                v = l.split(":", 1)[1]
                counts[v] = counts.get(v, 0) + 1
    return counts


def pick_vendor(row, vendor_restrict, capacity, cooldown, running_counts):
    for opt in row.get("options", []):
        v = opt["vendor"]
        if vendor_restrict and v not in vendor_restrict:
            continue
        if vendor_available(v, opt, capacity, cooldown, running_counts):
            return opt
    return None


def list_worktrees():
    """`orca worktree list --json` wraps rows at `result.worktrees`, not
    top-level `worktrees` — verified 2026-09-11 against a live run."""
    ok, out = run_orca(["worktree", "list", "--json"])
    if not ok:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return data
    result = data.get("result") if isinstance(data.get("result"), dict) else data
    return result.get("worktrees", []) if isinstance(result, dict) else []


def find_worktree(name_prefix):
    """Reuse an existing review-<n>/issue-<n> worktree instead of creating a
    -2/-3 suffixed copy. Matches on exact name or name-<n> prefix. Rows carry
    the name under `displayName`, not `name`."""
    for w in list_worktrees():
        wname = w.get("displayName") or w.get("name") or ""
        if wname == name_prefix or wname.startswith(name_prefix + "-"):
            return w
    return None


def run_in_worktree(cmd, cwd, log_path=None, timeout=REVIEWER_TIMEOUT_S):
    """Run cmd in cwd (a worktree). Optionally writes combined stdout+stderr
    to log_path. Returns (ok, stdout)."""
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"# command failed: {' '.join(cmd)}\n#   timed out after {timeout}s")
        return False, ""
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w", encoding="utf-8", errors="replace") as f:
            f.write(out.stdout or "")
            f.write(out.stderr or "")
    ok = out.returncode == 0
    if not ok:
        _fail_detail(cmd, out)
    return ok, out.stdout


def build_reviewer_cmd(opt, row, brief):
    """Headless reviewer launch command — no interactive TUI."""
    if opt["vendor"] == "codex":
        return ["codex", "exec", "-s", "danger-full-access", brief]
    if opt["vendor"] == "antigravity":
        # Google's Antigravity CLI (`agy`): Gemini and Sonnet ids, headless -p.
        cmd = ["agy", "-p", brief, "--model", opt["model"],
               "--dangerously-skip-permissions", "--output-format", "text",
               "--print-timeout", f"{REVIEWER_TIMEOUT_S // 60}m"]
        if "effort" in opt:
            cmd += ["--effort", opt["effort"]]
        return cmd
    return ["claude", "--model", opt["model"], "-p", brief,
            "--max-turns", str(row.get("max_turns", 20)),
            "--allowedTools", "Bash(gh:*)", "Bash(git:*)", "Bash(python:*)",
            "Read", "Grep", "Glob"]


def brief_file_path(first_number):
    return BRIEFS_DIR / f"issue-{first_number}" / "brief.md"


def worktree_path(w_or_json):
    """Best-effort filesystem path extraction from an `orca worktree` dict
    or raw JSON string. `list --json` rows and `create --json` results carry
    the path embedded in `id` as `<uuid>::<path>`, sometimes alongside a
    separate `path` key; `create` may nest the row under `worktree`."""
    data = w_or_json
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    if isinstance(data.get("result"), dict):
        data = data["result"]
    row = data.get("worktree") if isinstance(data.get("worktree"), dict) else data
    path = row.get("path")
    if path:
        return path
    wid = row.get("id") or row.get("worktreeId") or data.get("id")
    if isinstance(wid, str) and "::" in wid:
        return wid.split("::", 1)[1]
    return wid


def _looks_like_path(p):
    return bool(p) and isinstance(p, str) and ("/" in p or "\\" in p)


FIXED_SPARSE_PATHS = [
    "AGENTS.md", "CLAUDE.md", ".claude/", ".github/", "src/",
    "assets/Tests/", "tools/", "docs/architecture/tr/",
    "docs/architecture/control-manifest*", "Packages/", "ProjectSettings/",
]


def build_sparse_paths(row, issue_files):
    paths = set(row.get("match", {}).get("paths", []) or [])
    paths.update(FIXED_SPARSE_PATHS)
    paths.update(issue_files)
    return sorted(paths)


def collect_issue_files(issues):
    files = set()
    for i in issues:
        for line in extract_files_section(i.get("body", "")).splitlines():
            line = line.strip("- ").strip()
            if line:
                files.add(line)
    return files


def apply_sparse_checkout(wt_path, paths, dry_run):
    if dry_run:
        print(f"  sparse-checkout set: {paths}")
        return
    if not wt_path or not Path(wt_path).exists():
        print(f"# sparse-checkout skipped: no usable worktree path ({wt_path!r})")
        return
    cmd = ["git", "sparse-checkout", "set", "--no-cone"] + paths
    try:
        subprocess.run(cmd, cwd=wt_path, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        _fail_detail(cmd, e)


def slugify(title):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")
    return s[:40] or "issue"


def extract_files_section(body):
    if not body:
        return ""
    m = re.search(r"##\s*Files\s*\n(.*?)(\n##|\Z)", body, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def role_file_contents(role):
    if not role:
        return ""
    for base in [ROOT / ".claude" / "agents", ROOT / ".claude" / "agents" / "_catalog"]:
        p = base / f"{role}.md"
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
    return ""


def matching_rules(owned_paths):
    rules_dir = ROOT / ".claude" / "rules"
    matches = []
    if not rules_dir.exists():
        return matches
    for rf in rules_dir.glob("*.md"):
        text = rf.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"paths:\s*\n((?:\s*-\s*.+\n?)+)", text)
        if not m:
            continue
        globs = re.findall(r'-\s*"([^"]+)"', m.group(1))
        for g in globs:
            prefix = g.split("**")[0].split("*")[0]
            if any(op.startswith(prefix) for op in owned_paths):
                matches.append(rf)
                break
    return matches


def build_brief(issues, row, opt, owner_repo):
    numbers = [str(i["number"]) for i in issues]
    titles = "; ".join(f"#{i['number']} {i['title']}" for i in issues)
    closes = ", ".join(f"#{n}" for n in numbers)
    owned = set()
    role = None
    body_blocks = []
    for i in issues:
        role = role or role_from_labels(label_names(i))
        files = extract_files_section(i.get("body", ""))
        if files:
            for line in files.splitlines():
                line = line.strip("- ").strip()
                if line:
                    owned.add(line)
        body_blocks.append(f"### Issue #{i['number']}: {i['title']}\n\n{i.get('body', '')}")

    role_text = role_file_contents(role)
    rules_files = matching_rules(owned) if owned else []
    rules_text = "\n\n".join(rf.read_text(encoding="utf-8", errors="replace") for rf in rules_files)

    first = numbers[0]
    slug = slugify(issues[0]["title"])
    branch = f"task/{first}-batch" if len(issues) > 1 else f"task/{first}-{slug}"

    brief = f"""# Dispatch brief — {titles}

Routing row: {row['id']}  |  max_turns: {row.get('max_turns', 'n/a')}
Owned paths: {sorted(owned) or '(from issue bodies, none declared)'}

## Role
{role_text or '(no role file found)'}

## Rules
{rules_text or '(none matched)'}

## Issue bodies
{chr(10).join(body_blocks)}

## Worker contract
- Create branch {branch} from origin/main.
- Commit with an `Agent: {opt['vendor']}/{opt['model']}` trailer.
- Run `dotnet test Assets/Tests/Greenwood.Sim.Tests` if touching src/.
- Never touch lead-only paths (see .github/agent-routing.yaml row 'lead-only').
- Open a PR: `gh pr create --fill --body-file <file>` containing `Closes {closes}` and evidence.
- If the issue needs:unity, add label gate:queued.
- Finish with `orca orchestration worker_done` if dispatched under a Run, else end.
"""
    return brief, branch


AGENT_TRAILER_RE = re.compile(r"Agent:\s*([\w.\-]+)/([\w.\-]+)")
COMMENT_TOKENS = ("//", "#", "/*", "*", '"""', "'''", "<!--", "--")
DOCS_EXTS = (".md", ".txt")
DOCS_DIRS = ("docs/", "design/", "tasks/", "production/")


def review_row(routing):
    return next((r for r in routing.get("rows", []) if r["id"] == "review"), None)


def head_commit_vendor(pr_number):
    data = run_gh(["pr", "view", str(pr_number), "--json", "commits"])
    commits = data.get("commits", []) if isinstance(data, dict) else []
    if not commits:
        return None
    body = commits[-1].get("messageBody", "") or commits[-1].get("messageHeadline", "")
    m = AGENT_TRAILER_RE.search(body)
    return m.group(1) if m else None


def pr_files(pr_number):
    data = run_gh(["pr", "view", str(pr_number), "--json", "additions,deletions,files"])
    if not isinstance(data, dict):
        return [], 0
    files = data.get("files", [])
    changed = (data.get("additions") or 0) + (data.get("deletions") or 0)
    return files, changed


def is_docs_or_comment_only(pr_number, files):
    """docs-only: every path is under a docs dir or a .md/.txt file.
    comment-only: every +/- diff line (outside docs files) is blank or a
    comment token. Heuristic — good enough to skip an LLM review, not to
    approve code."""
    non_docs = [f["path"] for f in files
                if not (f["path"].lower().endswith(DOCS_EXTS)
                        or f["path"].startswith(DOCS_DIRS))]
    if not non_docs:
        return True
    patch = run_gh(["pr", "diff", str(pr_number), "--patch"], json_out=False)
    for line in patch.splitlines():
        if not (line.startswith("+") or line.startswith("-")):
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        text = line[1:].strip()
        if not text:
            continue
        if not text.startswith(COMMENT_TOKENS):
            return False
    return True


def existing_review_status(owner_repo, sha):
    out = run_gh(["api", f"repos/{owner_repo}/commits/{sha}/status",
                  "--jq", ".statuses[].context"], json_out=False)
    return {c.strip() for c in out.splitlines() if c.strip()}


def linked_issue(pr_number):
    data = run_gh(["pr", "view", str(pr_number), "--json", "body"])
    body = data.get("body", "") if isinstance(data, dict) else ""
    m = re.search(r"[Cc]loses\s+#(\d+)", body or "")
    return m.group(1) if m else None


def pick_review_option(row, authoring_vendor, changed, docs_or_comment):
    differing = [o for o in row["options"] if o["vendor"] != authoring_vendor]
    if not differing:
        return None, "no-vendor"
    if docs_or_comment:
        return None, "no-llm"
    if changed < 60:
        codex_opt = next((o for o in differing if o["vendor"] == "codex"), None)
        if codex_opt:
            return codex_opt, "cheap"
        claude_opt = next((o for o in differing if o["vendor"] == "claude"), None)
        return dict(claude_opt, effort="medium"), "cheap"
    return differing[0], "full"


DIFF_INLINE_CAP = 48_000  # bytes of diff pasted into the brief; larger diffs are read per file


def build_review_brief(pr_number, owner_repo, sha, opt, files, issue_num, max_turns=30):
    paths = {f["path"] for f in files}
    rules = matching_rules(paths)
    rules_text = "\n\n".join(rf.read_text(encoding="utf-8", errors="replace") for rf in rules)
    # Pre-fetch everything the reviewer would otherwise spend turns on: the
    # two 2026-09-11 reviewers of PR #72 exhausted 15 and then 30 turns on
    # fetch/checkout/issue/diff reads before posting anything.
    if issue_num:
        issue_body = run_gh(["issue", "view", str(issue_num), "--json", "title,body,comments",
                             "--jq", '"# " + .title + "\\n\\n" + .body + "\\n\\n"'
                                     ' + ([.comments[] | select(.body | startswith("Scope decision"))'
                                     ' | .body] | join("\\n\\n"))'], json_out=False)
    else:
        issue_body = "(none linked — judge against the PR body)"
    pr_body = run_gh(["pr", "view", str(pr_number), "--json", "body", "--jq", ".body"], json_out=False)
    stat = run_gh(["pr", "diff", str(pr_number), "--name-only"], json_out=False)
    diff = run_gh(["pr", "diff", str(pr_number)], json_out=False)
    if len(diff.encode("utf-8")) > DIFF_INLINE_CAP:
        diff = (f"(diff over {DIFF_INLINE_CAP // 1000} KB — read it per file with "
                f"`git diff origin/main...HEAD -- <path>`)")
    return f"""# Review brief — PR #{pr_number} ({owner_repo})

**Turn budget: {max_turns}.** Everything you need is in this brief. Spend at most 4 tool
calls reading extra context, and post the verdict (steps 6–7, one Bash call) no later
than turn {max_turns - 4}. Never run a test suite, never build, never explore beyond the
touched files. This worktree already has `refs/reviews/pr-{pr_number}` checked out, so a
touched file can be read directly by path when a hunk is not enough.

## Linked issue #{issue_num or '—'} — the acceptance is the standard
{issue_body}

## PR body
{pr_body}

## Files changed
{stat}
## Diff
```diff
{diff}
```

## Steps
1. Judge the diff against the acceptance above and any "Scope decision" comment quoted
   with it. Cite file:line for every finding.
2. Rules for the touched paths:
{rules_text or '(none matched)'}
3. Check the comment budget on any touched `.cs` file: `python tools/code/comment_budget.py check <file>`
6. GitHub rejects `gh pr review --approve/--request-changes` when the PR author
   is the same account as the reviewer (all our workers push as the same
   user) — do not attempt it. Instead post findings as a PR comment:
   - Write your findings to a file, first line "Review ({opt['vendor']}/{opt['model']}): APPROVE"
     or "Review ({opt['vendor']}/{opt['model']}): REQUEST CHANGES".
   - `gh pr comment {pr_number} --body-file <file>`
7. Set the review status on the PR **head sha** — use headRefOid
   (`gh pr view {pr_number} --json headRefOid`), never `git rev-parse HEAD`:
   `gh api repos/{owner_repo}/statuses/{sha} -f state=<success|failure> -f context=review -f description="{opt['vendor']}/{opt['model']}: <approve|changes>"`
8. On request-changes only: `gh issue edit {issue_num} --add-label status:in-progress --remove-label status:waiting` and comment the findings on issue #{issue_num}.
"""


def log_review_dispatch(pr_number, opt, band, worktree_id, profile=None):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d %H:%M UK")
    profile_str = f" | profile={profile}" if profile else ""
    line = (f"- {date} | review #{pr_number} | band={band} | "
            f"{opt['vendor']}/{opt['model']} | worktree={str(worktree_id).strip()[:80]}"
            f"{profile_str}\n")
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)


def reviews_main(live, dry_run, max_n, no_profile=False):
    routing = load_routing()
    row = review_row(routing)
    owner_repo = get_owner_repo()
    if row is None or not owner_repo:
        print("# no 'review' row or owner/repo; nothing to do")
        return

    # `--json …,commits` on the list query blows the GraphQL node-count limit
    # on this repo; commits are fetched per-PR instead, via head_commit_vendor.
    prs = run_gh(["pr", "list", "--state", "open", "--json",
                  "number,headRefName,labels,author", "--limit", "200"])
    prs = prs if isinstance(prs, list) else []

    launched = 0
    for pr in prs:
        if max_n is not None and launched >= max_n:
            break
        n = pr["number"]
        if not pr.get("headRefName", "").startswith("task/"):
            continue
        labels = label_names(pr)
        if "review:in-progress" in labels:
            print(f"pr #{n}: skipped (review:in-progress)")
            continue

        data = run_gh(["pr", "view", str(n), "--json", "headRefOid"])
        sha = data.get("headRefOid") if isinstance(data, dict) else None
        if not sha:
            print(f"pr #{n}: skipped (no head sha)")
            continue
        if "review" in existing_review_status(owner_repo, sha):
            print(f"pr #{n}: skipped (review status already set)")
            continue

        authoring_vendor = head_commit_vendor(n)
        if not authoring_vendor:
            print(f"pr #{n}: skipped (no Agent trailer on head commit)")
            continue

        files, changed = pr_files(n)
        docs_or_comment = is_docs_or_comment_only(n, files)
        opt, band = pick_review_option(row, authoring_vendor, changed, docs_or_comment)

        if band == "no-vendor":
            print(f"pr #{n}: skipped (no differing vendor; author={authoring_vendor})")
            continue

        if band == "no-llm":
            print(f"pr #{n}: band=no-llm changed={changed} -> post review=success, no launch")
            if not dry_run:
                run_gh(["api", f"repos/{owner_repo}/statuses/{sha}",
                        "-f", "state=success", "-f", "context=review",
                        "-f", "description=no code changed; CI only"], json_out=False)
            launched += 1
            continue

        issue_num = linked_issue(n)
        brief = build_review_brief(n, owner_repo, sha, opt, files, issue_num,
                                   max_turns=int(row.get("max_turns", 30)))
        reviewer_cmd = build_reviewer_cmd(opt, row, brief)
        log_path = REVIEW_LOGS_DIR / f"review-{n}.log"
        print(f"pr #{n}: band={band} changed={changed} author={authoring_vendor} "
              f"reviewer={opt['vendor']}/{opt['model']}")
        print(f"  headless reviewer cmd: {reviewer_cmd}")
        print(f"  log: {log_path}")

        review_ref = f"refs/reviews/pr-{n}"
        fetch_cmd = ["git", "fetch", "--force", "origin", f"refs/pull/{n}/head:{review_ref}"]
        checkout_cmd = ["git", "checkout", "--detach", review_ref]
        print(f"  checkout cmd: {fetch_cmd}")
        print(f"  checkout cmd: {checkout_cmd}")
        if not no_profile:
            apply_profile(None, "lead", dry_run=True)

        name = f"review-{n}"
        reused = find_worktree(name)
        if dry_run:
            if reused:
                print(f"  worktree path: {worktree_path(reused)}")
            launched += 1
            continue

        # Headless launch — the interactive TUI stalls on config prompts.
        # Worktree first, then a detached checkout inside it, then run the
        # reviewer CLI directly via subprocess with a 900s timeout.
        worktree_id = None
        wt_path = None
        if reused:
            print(f"pr #{n}: reusing existing worktree {reused.get('name')}")
            worktree_id = json.dumps(reused)
            wt_path = worktree_path(reused)
        else:
            ok, out = run_orca(["worktree", "create", "--name", name,
                                 "--no-parent", "--json"])
            worktree_id = out
            wt_path = worktree_path(out)
            if not _looks_like_path(wt_path):
                # create's id sometimes lacks the embedded path — re-resolve
                # via `worktree list`, which always carries `id::path`.
                relisted = find_worktree(name)
                if relisted:
                    wt_path = worktree_path(relisted)
            if not ok:
                print(f"# review worktree create failed for pr #{n}")
                continue

        if not wt_path or not Path(wt_path).exists():
            print(f"# review dispatch skipped for pr #{n}: no usable worktree path ({wt_path!r})")
            continue

        # `gh pr checkout` fails when the worker's own worktree already holds
        # the PR's branch ("already used by worktree at .../issue-<n>") — a
        # detached checkout of the fetched PR ref sidesteps that entirely.
        ok_fetch, _ = run_in_worktree(fetch_cmd, cwd=wt_path)
        ok_co = False
        if ok_fetch:
            ok_co, _ = run_in_worktree(checkout_cmd, cwd=wt_path)
        if not ok_co:
            print(f"# pr checkout failed for pr #{n}")
            continue

        if not no_profile:
            apply_profile(wt_path, "lead", dry_run=False)

        ok_run, _ = run_in_worktree(reviewer_cmd, cwd=wt_path, log_path=log_path)
        if not ok_run:
            print(f"# reviewer run failed for pr #{n} (see {log_path})")
            continue

        run_gh(["pr", "edit", str(n), "--add-label", "review:in-progress"], json_out=False)
        log_review_dispatch(n, opt, band, worktree_id, profile=None if no_profile else "lead")
        launched += 1

    print(f"# reviews pass complete: {launched} decision(s), dry_run={dry_run}")


WORKTREE_NAME_RE = re.compile(r"^(issue|review)-(\d+)(?:-\d+)?$")


def worktree_is_done(kind, number, owner_repo):
    """issue-N is done when issue N is closed or its task/N-* PR is merged or
    closed; review-N is done when PR N is closed/merged or its head already
    carries a `review` status (the reviewer has posted)."""
    if kind == "issue":
        st = run_gh(["issue", "view", str(number), "--json", "state", "--jq", ".state"], json_out=False).strip()
        if st == "CLOSED":
            return True
        prs = run_gh(["pr", "list", "--state", "all", "--search", f"head:task/{number}-",
                      "--json", "state", "--limit", "5"])
        return bool(prs) and all(p.get("state") in ("MERGED", "CLOSED") for p in prs)
    pr = run_gh(["pr", "view", str(number), "--json", "state,headRefOid"])
    if not isinstance(pr, dict):
        return False
    if pr.get("state") in ("MERGED", "CLOSED"):
        return True
    return "review" in existing_review_status(owner_repo, pr.get("headRefOid", ""))


def cleanup_main(dry_run, quiet=False):
    """Remove issue-N / review-N worktrees whose work has concluded: close
    their Orca terminals, `orca worktree rm`, delete the local task branch
    and prune. Runs at the start of every dispatch pass (USER 2026-09-11:
    worktrees are managed automatically when they reach their conclusion)."""
    owner_repo = get_owner_repo()
    removed = 0
    for w in list_worktrees():
        name = w.get("displayName") or w.get("name") or ""
        m = WORKTREE_NAME_RE.match(name)
        if not m:
            continue
        kind, number = m.group(1), int(m.group(2))
        if not worktree_is_done(kind, number, owner_repo):
            continue
        branch = (w.get("branch") or "").replace("refs/heads/", "")
        print(f"# cleanup: {name} ({kind} #{number} concluded){' [dry-run]' if dry_run else ''}")
        if dry_run:
            continue
        run_orca(["terminal", "close", "--worktree", f"name:{name}", "--all", "--json"])
        ok, _ = run_orca(["worktree", "rm", "--worktree", f"name:{name}", "--force", "--json"])
        if not ok:
            print(f"#   orca worktree rm failed for {name}; left in place")
            continue
        subprocess.run(["git", "worktree", "prune"], cwd=ROOT, capture_output=True)
        if branch.startswith("task/"):
            subprocess.run(["git", "branch", "-D", branch], cwd=ROOT, capture_output=True)
        removed += 1
    if not quiet:
        print(f"# cleanup: {removed} worktree(s) removed")


def main():
    ap = argparse.ArgumentParser(description="Orca dispatch loop")
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--max", type=int, default=2)
    ap.add_argument("--only", type=int, default=None)
    ap.add_argument("--reviews", action="store_true",
                     help="Dispatch PR reviews instead of the issue queue")
    ap.add_argument("--no-sparse", action="store_true",
                     help="Skip applying per-role sparse-checkout to a new worktree")
    ap.add_argument("--no-profile", action="store_true",
                     help="Skip installing a framework profile into the worktree")
    ap.add_argument("--cleanup", action="store_true",
                     help="Only remove concluded issue-N / review-N worktrees, then exit")
    args = ap.parse_args()

    live = args.live
    dry_run = not live

    # Every pass starts by releasing worktrees whose issue or review concluded.
    cleanup_main(dry_run, quiet=not args.cleanup)
    if args.cleanup:
        return

    if args.reviews:
        reviews_main(live, dry_run, args.max, no_profile=args.no_profile)
        return

    routing = load_routing()
    capacity = routing.get("capacity", {})
    cooldown = routing.get("cooldown", {})

    owner_repo = get_owner_repo()
    if not owner_repo:
        print("# could not resolve owner/repo via gh repo view; blocked-by checks will be skipped")

    issues = run_gh(
        ["issue", "list", "-l", "status:ready", "--state", "open", "--limit", "200",
         "--json", "number,title,labels,body,milestone"]
    )
    if not isinstance(issues, list):
        issues = []

    skip_labels = {"tier:lead", "size:L", "status:waiting"}
    queue = []
    for i in issues:
        if args.only and i["number"] != args.only:
            continue
        labels = label_names(i)
        if not args.only and (labels & skip_labels):
            print(f"issue #{i['number']}: skipped (label {labels & skip_labels})")
            continue
        if owner_repo and is_blocked(i["number"], owner_repo):
            print(f"issue #{i['number']}: skipped (open blocker)")
            continue
        queue.append(i)

    queue.sort(key=lambda i: (milestone_key(i), i["number"]))

    running_counts = running_worker_counts()
    launched = 0
    used_numbers = set()

    i = 0
    while i < len(queue) and launched < args.max:
        issue = queue[i]
        if issue["number"] in used_numbers:
            i += 1
            continue
        labels = label_names(issue)
        role = role_from_labels(labels)
        stage = stage_from_labels(labels)
        if role == "unassigned":
            print(f"issue #{issue['number']}: needs triage")
            i += 1
            continue
        row = match_row(routing, role, stage)
        if row is None:
            print(f"issue #{issue['number']}: no matching routing row (role={role}, stage={stage})")
            i += 1
            continue

        vendor_restrict = vendor_from_labels(labels)
        opt = pick_vendor(row, vendor_restrict, capacity, cooldown, running_counts)
        if opt is None:
            print(f"issue #{issue['number']}: waiting (no free vendor for row {row['id']})")
            i += 1
            continue

        batch = [issue]
        ms = milestone_key(issue)
        j = i + 1
        while len(batch) < BATCH_SIZE and j < len(queue):
            cand = queue[j]
            cand_labels = label_names(cand)
            cand_role = role_from_labels(cand_labels)
            cand_stage = stage_from_labels(cand_labels)
            cand_row = match_row(routing, cand_role, cand_stage)
            if (cand_row and cand_row["id"] == row["id"]
                    and milestone_key(cand) == ms
                    and "size:L" not in cand_labels):
                batch.append(cand)
                j += 1
            else:
                break

        brief, branch = build_brief(batch, row, opt, owner_repo)
        numbers = [b["number"] for b in batch]
        wt_name = f"issue-{numbers[0]}"
        brief_path = brief_file_path(numbers[0])
        sparse_paths = build_sparse_paths(row, collect_issue_files(batch))
        print(f"issue(s) #{','.join(str(n) for n in numbers)}: row={row['id']} "
              f"vendor={opt['vendor']} model={opt['model']} branch={branch} "
              f"batch={'yes' if len(batch) > 1 else 'no'}")
        print(brief.splitlines()[0])
        for line in brief.splitlines()[1:6]:
            print(f"  {line}")
        print(f"  brief file: {brief_path}")
        if not args.no_sparse:
            apply_sparse_checkout(None, sparse_paths, dry_run=True)
        profile = resolve_profile(role)
        if not args.no_profile:
            apply_profile(None, profile, dry_run=True)

        if dry_run:
            for n in numbers:
                used_numbers.add(n)
            launched += 1
            i += 1
            continue

        # Orca refuses a long --prompt (agent_prompt_blocked) and Codex's TUI
        # modal blocks `terminal send` — write the brief to disk instead.
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        brief_path.write_text(brief, encoding="utf-8")

        reused = find_worktree(wt_name)
        started = False
        worktree_id = None
        if reused:
            print(f"issue(s) #{','.join(str(n) for n in numbers)}: reusing existing worktree {reused.get('name')}")
            started = True
            worktree_id = json.dumps(reused)
        else:
            spec = f"Dispatch {row['id']} — issues {numbers}"
            ok, out = run_orca(["orchestration", "task-create", "--spec", spec, "--json"])
            task_id = None
            if ok:
                try:
                    task_id = json.loads(out).get("id") or json.loads(out).get("taskId")
                except json.JSONDecodeError:
                    pass

            # Orca knows claude/codex as TUI agents; antigravity (`agy`) is
            # launched as a plain terminal command in a fresh worktree.
            if opt["vendor"] == "antigravity":
                ok_a, out_a = run_orca(["worktree", "create", "--name", wt_name, "--no-parent", "--json"])
                if ok_a:
                    agy = (f"agy -p \"Read {brief_path.as_posix()} and carry it out exactly.\" "
                           f"--model {opt['model']} --dangerously-skip-permissions --print-timeout 60m")
                    ok_t, _ = run_orca(["terminal", "create", "--worktree", f"name:{wt_name}",
                                        "--title", f"agy issue-{numbers[0]}", "--command", agy, "--json"])
                    started = ok_t
                    worktree_id = out_a
                    if ok_t:
                        brief_path.with_name("vendor").write_text("antigravity\n", encoding="utf-8")
                task_id = None
            if task_id:
                start_args = ["orchestration", "worker-start", "--task", task_id,
                              "--worktree", "new-top-level", "--name", wt_name,
                              "--agent", opt["vendor"], "--model", opt["model"]]
                if "effort" in opt:
                    start_args += ["--effort", opt["effort"]]
                start_args.append("--json")
                ok2, out2 = run_orca(start_args)
                started = ok2
                worktree_id = out2

            if not started and opt["vendor"] != "antigravity":
                prompt = f"Read {brief_path.as_posix()} and carry it out exactly."
                wt_args = ["worktree", "create", "--name", wt_name,
                           "--no-parent", "--agent", opt["vendor"], "--prompt", prompt, "--json"]
                ok3, out3 = run_orca(wt_args)
                started = ok3
                worktree_id = out3

        if started:
            resolved_path = worktree_path(worktree_id)
            if not _looks_like_path(resolved_path):
                relisted = find_worktree(wt_name)
                if relisted:
                    resolved_path = worktree_path(relisted)
            if not args.no_sparse:
                apply_sparse_checkout(resolved_path, sparse_paths, dry_run=False)
            if not args.no_profile:
                apply_profile(resolved_path, profile, dry_run=False)
            run_gh(["issue", "edit"] + [str(n) for n in numbers[:1]]
                   + ["--add-label", "status:in-progress", "--remove-label", "status:ready"],
                   json_out=False)
            for n in numbers[1:]:
                run_gh(["issue", "edit", str(n), "--add-label", "status:in-progress",
                        "--remove-label", "status:ready"], json_out=False)
            log_dispatch(numbers, row["id"], opt, worktree_id, len(batch) > 1,
                         profile=None if args.no_profile else profile)
            for n in numbers:
                used_numbers.add(n)
            launched += 1
        else:
            print(f"# dispatch failed for issues {numbers}")

        i += 1

    print(f"# pass complete: {launched} dispatch(es), dry_run={dry_run}")


def log_dispatch(numbers, row_id, opt, worktree_id, batched, profile=None):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d %H:%M UK")
    issues_str = ",".join(f"#{n}" for n in numbers)
    profile_str = f" | profile={profile}" if profile else ""
    line = (f"- {date} | {issues_str} | row={row_id} | "
            f"{opt['vendor']}/{opt['model']} | worktree={worktree_id.strip()[:80]} | "
            f"batch={'yes' if batched else 'no'}{profile_str}\n")
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)


if __name__ == "__main__":
    main()

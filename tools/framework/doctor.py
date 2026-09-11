#!/usr/bin/env python3
"""Framework health checks — skills, agents, rules, CLAUDE.md, hooks, routing, engine overlay.

Rules are read from framework/rules plus engines/<engine>/rules when
framework/engine.txt names an engine (the file is optional). Skills are read
from .claude/skills when installed, else from .agents/skills.

Modes:
  --warn (default) — print a table of results, exit 0 regardless.
  --strict          — print the table, exit 1 if any check has failures.

Extra:
  --stage <name>    — list skills whose `stages:` frontmatter excludes the
                       given stage (would be disabled by a profile filter).

Exit codes:
  0 — no failures, or --warn mode
  1 — failures found in --strict mode
  2 — script error (missing dependency, bad path)
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-16"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

try:
    import yaml
except ImportError:
    print("error: PyYAML is required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
SKILLS_SOURCE_DIR = REPO_ROOT / ".agents" / "skills"
AGENTS_DIR = REPO_ROOT / ".claude" / "agents"
RULES_DIR = REPO_ROOT / "framework" / "rules"
ENGINE_FILE = REPO_ROOT / "framework" / "engine.txt"
ENGINES_DIR = REPO_ROOT / "engines"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
SETTINGS_JSON = REPO_ROOT / ".claude" / "settings.json"
ROUTING_YAML = REPO_ROOT / ".github" / "agent-routing.yaml"
ROUTING_VALIDATOR = REPO_ROOT / "tools" / "ci" / "validate-agent-routing.py"

DESC_CAP = 160
RULE_CAP_BYTES = 3072
CLAUDE_MD_CAP_BYTES = 16 * 1024
AGENT_MAX_TURNS_CAP = 25


def _read_frontmatter(path):
    """Split a file into (frontmatter_dict, ok, error) using the first --- block.

    Rules may also open with a bare `paths:` line closed by `---`, the form
    tools/framework/sync.py accepts.
    """
    text = path.read_text(encoding="utf-8")
    if text.startswith("paths:"):
        text = "---\n" + text
    if not text.startswith("---"):
        return None, False, "does not start with ---"
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, False, "no closing --- for frontmatter"
    try:
        data = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:
        return None, False, f"YAML parse error: {exc}"
    return data, True, None


def _skills_dir():
    """.claude/skills when installed, else the authored .agents/skills."""
    return SKILLS_DIR if SKILLS_DIR.is_dir() else SKILLS_SOURCE_DIR


def _engine_name():
    """Engine overlay named by framework/engine.txt, or None (the file is optional)."""
    if not ENGINE_FILE.is_file():
        return None
    return ENGINE_FILE.read_text(encoding="utf-8").strip() or None


def _rule_source_dirs():
    """framework/rules plus engines/<engine>/rules when an engine is selected."""
    dirs = [RULES_DIR]
    engine = _engine_name()
    if engine:
        dirs.append(ENGINES_DIR / engine / "rules")
    return dirs


def check_skills():
    """(a) Every SKILL.md has name, description <=160 chars, stages."""
    failures = []
    total = 0
    skills_dir = _skills_dir()
    if not skills_dir.is_dir():
        return 0, [f"{skills_dir}: does not exist"]
    for skill_dir in sorted(skills_dir.iterdir()):
        path = skill_dir / "SKILL.md"
        if not path.is_file():
            continue
        total += 1
        data, ok, err = _read_frontmatter(path)
        if not ok:
            failures.append(f"{skill_dir.name}: {err}")
            continue
        if not data.get("name"):
            failures.append(f"{skill_dir.name}: missing name")
        desc = data.get("description", "")
        if not desc:
            failures.append(f"{skill_dir.name}: missing description")
        elif len(desc) > DESC_CAP:
            failures.append(f"{skill_dir.name}: description {len(desc)} chars (cap {DESC_CAP})")
        if "stages" not in data:
            failures.append(f"{skill_dir.name}: missing stages")
    return total, failures


def check_agents():
    """(b) Every .claude/agents/*.md (not _catalog) has name, description <=160, model, maxTurns <=25."""
    failures = []
    total = 0
    for path in sorted(AGENTS_DIR.glob("*.md")):
        total += 1
        data, ok, err = _read_frontmatter(path)
        if not ok:
            failures.append(f"{path.name}: {err}")
            continue
        if not data.get("name"):
            failures.append(f"{path.name}: missing name")
        desc = data.get("description", "")
        if not desc:
            failures.append(f"{path.name}: missing description")
        elif len(desc) > DESC_CAP:
            failures.append(f"{path.name}: description {len(desc)} chars (cap {DESC_CAP})")
        if not data.get("model"):
            failures.append(f"{path.name}: missing model")
        max_turns = data.get("maxTurns")
        if max_turns is None:
            failures.append(f"{path.name}: missing maxTurns")
        elif max_turns > AGENT_MAX_TURNS_CAP:
            failures.append(f"{path.name}: maxTurns {max_turns} (cap {AGENT_MAX_TURNS_CAP})")
    return total, failures


def _check_rule_files(paths):
    failures = []
    total = 0
    for path in paths:
        total += 1
        label = path.relative_to(REPO_ROOT).as_posix()
        size = path.stat().st_size
        if size > RULE_CAP_BYTES:
            failures.append(f"{label}: {size} bytes (cap {RULE_CAP_BYTES})")
        data, ok, err = _read_frontmatter(path)
        if not ok:
            failures.append(f"{label}: {err}")
            continue
        if "paths" not in data:
            failures.append(f"{label}: missing paths")
    return total, failures


def check_rules():
    """(c) Every authored rule (framework/rules + the selected engine overlay) <=cap with `paths:`."""
    failures = []
    paths = []
    engine = _engine_name()
    if engine and not (ENGINES_DIR / engine / "rules").is_dir():
        failures.append(f"framework/engine.txt names '{engine}' but engines/{engine}/rules is missing")
    for directory in _rule_source_dirs():
        if directory.is_dir():
            paths.extend(sorted(directory.glob("*.md")))
    if not paths:
        failures.append(f"{RULES_DIR}: no authored rules found")
    total, rule_failures = _check_rule_files(paths)
    return total, failures + rule_failures


def check_engine_rules():
    """(h) Every engines/*/rules/*.md carries a `paths:` header like the generic rules."""
    if not ENGINES_DIR.is_dir():
        return 0, []
    return _check_rule_files(sorted(ENGINES_DIR.glob("*/rules/*.md")))


def check_claude_md():
    """(d) CLAUDE.md <=16 KB."""
    if not CLAUDE_MD.is_file():
        return 0, [f"{CLAUDE_MD}: does not exist"]
    size = CLAUDE_MD.stat().st_size
    if size > CLAUDE_MD_CAP_BYTES:
        return 1, [f"CLAUDE.md: {size} bytes (cap {CLAUDE_MD_CAP_BYTES})"]
    return 1, []


def check_hooks():
    """(e) settings.json hooks reference only scripts that exist."""
    if not SETTINGS_JSON.is_file():
        return 0, [f"{SETTINGS_JSON}: does not exist"]
    data = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
    hooks = data.get("hooks", {})
    checked = []
    failures = []
    for event, groups in hooks.items():
        for group in groups:
            for hook in group.get("hooks", []):
                command = hook.get("command", "")
                for token in command.replace('"', " ").split():
                    token = token.replace("$CLAUDE_PROJECT_DIR", str(REPO_ROOT))
                    if token.endswith(".sh") or token.endswith(".py"):
                        checked.append(token)
                        script_path = Path(token)
                        if not script_path.is_absolute():
                            script_path = REPO_ROOT / token
                        if not script_path.is_file():
                            failures.append(f"{event}: script not found: {token}")
    return len(checked), failures


def check_routing():
    """(f) .github/agent-routing.yaml validates via validate-agent-routing.py's checker."""
    if not ROUTING_VALIDATOR.is_file():
        return 0, [f"{ROUTING_VALIDATOR}: does not exist"]
    spec = importlib.util.spec_from_file_location("validate_agent_routing", ROUTING_VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ok, msg = module.validate_routing_yaml(ROUTING_YAML)
    if ok:
        return 1, []
    return 1, [f"{ROUTING_YAML}: {msg}"]


def check_stage_filter(stage):
    """(g) list skills whose stages exclude the given stage."""
    excluded = []
    for skill_dir in sorted(_skills_dir().iterdir()):
        path = skill_dir / "SKILL.md"
        if not path.is_file():
            continue
        data, ok, _err = _read_frontmatter(path)
        if not ok:
            continue
        stages = data.get("stages") or []
        if stage not in stages:
            excluded.append(skill_dir.name)
    return excluded


CHECKS = [
    ("skills (a)", check_skills),
    ("agents (b)", check_agents),
    ("rules (c)", check_rules),
    ("CLAUDE.md (d)", check_claude_md),
    ("hooks (e)", check_hooks),
    ("routing (f)", check_routing),
    ("engine rules (h)", check_engine_rules),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--warn", action="store_true")
    parser.add_argument("--stage", help="list skills excluded from this stage")
    args = parser.parse_args()
    strict = args.strict and not args.warn

    if args.stage:
        excluded = check_stage_filter(args.stage)
        print(f"Skills excluded from stage '{args.stage}': {len(excluded)}")
        for name in excluded:
            print(f"  {name}")
        return 0

    any_failures = False
    rows = []
    for label, fn in CHECKS:
        total, failures = fn()
        rows.append((label, total, failures))
        if failures:
            any_failures = True

    print(f"{'check':<18}{'checked':>10}{'failed':>10}")
    for label, total, failures in rows:
        print(f"{label:<18}{total:>10}{len(failures):>10}")
    print()
    for label, _total, failures in rows:
        for f in failures:
            print(f"[{label}] {f}")

    if strict and any_failures:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

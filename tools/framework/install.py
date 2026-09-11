#!/usr/bin/env python3
"""Install a framework profile — decides which skills a checkout enables.

Replaces the single .claude/skills junction (-> .agents/skills) with a real
directory holding one per-skill junction, filtered by the chosen profile's
`skills:` list and the current stage's `stages:` frontmatter. Writes
.claude/profile.json recording what was installed. `--reset` restores the
original single junction.

`--engine <name>` selects an engine overlay: writes framework/engine.txt,
copies engines/<name>/workflows/*.yml into .github/workflows/ and
engines/<name>/profiles/*.yaml into framework/profiles/ (never overwriting),
then runs tools/framework/sync.py so the overlay's rules are generated.

This module does not touch .claude/agents — hiding roles per worktree is a
follow-up, not part of this profile mechanism.
"""

import argparse
import datetime
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
SKILLS_LINK = REPO_ROOT / ".claude" / "skills"
SKILLS_TARGET = REPO_ROOT / ".agents" / "skills"
PROFILES_DIR = REPO_ROOT / "framework" / "profiles"
STAGE_FILE = REPO_ROOT / "production" / "stage.txt"
PROFILE_JSON = REPO_ROOT / ".claude" / "profile.json"
ENGINE_FILE = REPO_ROOT / "framework" / "engine.txt"
ENGINES_DIR = REPO_ROOT / "engines"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
SYNC_SCRIPT = REPO_ROOT / "tools" / "framework" / "sync.py"


def read_stage():
    if not STAGE_FILE.is_file():
        return None
    return STAGE_FILE.read_text(encoding="utf-8").strip().lower().replace(" ", "-")


def all_skill_names():
    return sorted(p.name for p in SKILLS_TARGET.iterdir() if (p / "SKILL.md").is_file())


def skill_stages(name):
    path = SKILLS_TARGET / name / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return []
    parts = text.split("---", 2)
    if len(parts) < 3:
        return []
    data = yaml.safe_load(parts[1]) or {}
    return data.get("stages") or []


def clear_skills_link():
    is_junction = hasattr(Path, "is_junction") and SKILLS_LINK.is_junction()
    if SKILLS_LINK.is_symlink() or is_junction:
        SKILLS_LINK.unlink()
    elif SKILLS_LINK.is_dir():
        try:
            SKILLS_LINK.rmdir()
        except OSError:
            import shutil
            shutil.rmtree(SKILLS_LINK)
    elif SKILLS_LINK.exists():
        SKILLS_LINK.unlink()


def mklink_junction(link, target):
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        check=True, capture_output=True, text=True,
    )


def do_reset():
    clear_skills_link()
    mklink_junction(SKILLS_LINK, SKILLS_TARGET)
    if PROFILE_JSON.exists():
        PROFILE_JSON.unlink()
    print(f"reset: {SKILLS_LINK} -> {SKILLS_TARGET}")


def _copy_overlay(source_dir, target_dir, pattern):
    """Copy files matching pattern from source_dir into target_dir, skipping existing ones."""
    copied, skipped = [], []
    if not source_dir.is_dir():
        return copied, skipped
    target_dir.mkdir(parents=True, exist_ok=True)
    for src in sorted(source_dir.glob(pattern)):
        dst = target_dir / src.name
        if dst.exists():
            skipped.append(src.name)
            continue
        shutil.copyfile(src, dst)
        copied.append(src.name)
    return copied, skipped


def do_engine(engine_name):
    engine_dir = ENGINES_DIR / engine_name
    if not engine_dir.is_dir():
        available = sorted(p.name for p in ENGINES_DIR.iterdir() if p.is_dir()) if ENGINES_DIR.is_dir() else []
        print(f"error: no engine overlay at {engine_dir}; available: {available or 'none'}", file=sys.stderr)
        sys.exit(2)

    ENGINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENGINE_FILE.write_text(engine_name + "\n", encoding="utf-8")
    print(f"engine: wrote {ENGINE_FILE.relative_to(REPO_ROOT).as_posix()} = {engine_name}")

    for label, src, dst, pattern in (
        ("workflows", engine_dir / "workflows", WORKFLOWS_DIR, "*.yml"),
        ("profiles", engine_dir / "profiles", PROFILES_DIR, "*.yaml"),
    ):
        copied, skipped = _copy_overlay(src, dst, pattern)
        print(f"engine: {label} copied {copied or 'none'}; kept existing {skipped or 'none'}")

    result = subprocess.run([sys.executable, str(SYNC_SCRIPT)], cwd=REPO_ROOT)
    if result.returncode != 0:
        print("error: tools/framework/sync.py failed after selecting the engine", file=sys.stderr)
        sys.exit(result.returncode)


def do_install(profile_name):
    profile_path = PROFILES_DIR / f"{profile_name}.yaml"
    if not profile_path.is_file():
        available = sorted(p.stem for p in PROFILES_DIR.glob("*.yaml")) if PROFILES_DIR.is_dir() else []
        print(
            f"error: profile '{profile_name}' not found in {PROFILES_DIR} "
            f"(available: {', '.join(available) or 'none'}; an engine overlay's profiles "
            f"arrive via --engine <name>)",
            file=sys.stderr,
        )
        sys.exit(2)
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}

    stage = (profile.get("stages") or [None])[0] or read_stage()

    requested = profile.get("skills")
    candidates = all_skill_names() if requested == "all" else list(requested or [])

    enabled = [s for s in candidates if stage is None or stage in skill_stages(s)]

    clear_skills_link()
    SKILLS_LINK.mkdir(parents=True)
    for name in enabled:
        mklink_junction(SKILLS_LINK / name, SKILLS_TARGET / name)

    PROFILE_JSON.write_text(json.dumps({
        "profile": profile_name,
        "stage": stage,
        "skills": enabled,
        "roles": profile.get("roles") or [],
        "installed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }, indent=2), encoding="utf-8")

    print(f"installed profile '{profile_name}' ({len(enabled)} skills, stage={stage})")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--profile", help="install this profile's skill set (framework/profiles/<name>.yaml)")
    group.add_argument("--reset", action="store_true", help="restore the single .claude/skills junction")
    parser.add_argument("--engine", help="select an engine overlay from engines/<name>/ and run sync")
    args = parser.parse_args()
    if not (args.engine or args.profile or args.reset):
        parser.error("one of --engine, --profile or --reset is required")

    if args.engine:
        do_engine(args.engine)
    if args.reset:
        do_reset()
    elif args.profile:
        do_install(args.profile)


if __name__ == "__main__":
    main()

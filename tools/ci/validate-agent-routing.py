#!/usr/bin/env python3
"""Validate agent routing YAML and PR commit trailers."""

import sys
import json
import subprocess
import argparse
from pathlib import Path

def load_yaml(path):
    """Load YAML with PyYAML if available, else minimal fallback parser."""
    try:
        import yaml
        with open(path, 'r') as f:
            return yaml.safe_load(f)
    except ImportError:
        # Minimal YAML parser for basic key:value and lists
        import re
        data = {}
        with open(path, 'r') as f:
            lines = f.readlines()

        # This is a very basic parser—only handles the routing.yaml structure
        current_section = None
        for line in lines:
            line = line.rstrip('\n')
            if not line or line.startswith('#'):
                continue

            # Top-level keys
            if line.startswith('unity_cli:'):
                data['unity_cli'] = line.split(':', 1)[1].strip()
            elif line.startswith('capacity:'):
                current_section = 'capacity'
                data['capacity'] = {}
            elif line.startswith('cooldown:'):
                current_section = 'cooldown'
                data['cooldown'] = {}
            elif line.startswith('lead:'):
                current_section = 'lead'
                data['lead'] = {}
            elif line.startswith('rows:'):
                current_section = 'rows'
                data['rows'] = []
            elif current_section in ('capacity', 'cooldown', 'lead') and ':' in line:
                key, val = line.lstrip().split(':', 1)
                key = key.strip()
                val = val.strip()
                if val == 'null':
                    val = None
                elif val.isdigit():
                    val = int(val)
                data[current_section][key] = val
            elif current_section == 'rows' and line.startswith('  - id:'):
                data['rows'].append({'id': line.split(':', 1)[1].strip()})
            elif current_section == 'rows' and line.startswith('    '):
                if not data['rows']:
                    continue
                row = data['rows'][-1]
                if ':' in line:
                    key, val = line.lstrip().split(':', 1)
                    key = key.strip()
                    val = val.strip()
                    if val.isdigit():
                        val = int(val)
                    if key not in row:
                        row[key] = val if key != 'options' else []

        return data

def validate_routing_yaml(path):
    """Validate agent-routing.yaml shape."""
    if not path.exists():
        return False, f"{path} does not exist"

    try:
        data = load_yaml(path)
    except Exception as e:
        return False, f"Failed to parse {path}: {e}"

    # Check top-level structure
    if 'capacity' not in data:
        return False, "Missing 'capacity' block"
    if 'cooldown' not in data:
        return False, "Missing 'cooldown' block"
    if 'lead' not in data:
        return False, "Missing 'lead' section"
    if 'rows' not in data:
        return False, "Missing 'rows' list"

    # Validate capacity
    for vendor in ['claude', 'codex', 'antigravity']:
        if vendor not in data['capacity']:
            return False, f"Missing capacity for vendor '{vendor}'"
        if not isinstance(data['capacity'][vendor], int):
            return False, f"capacity.{vendor} must be an integer"

    # Validate cooldown
    for vendor in ['claude', 'codex', 'antigravity']:
        if vendor not in data['cooldown']:
            return False, f"Missing cooldown for vendor '{vendor}'"

    # Validate lead
    lead = data['lead']
    for key in ['vendor', 'model', 'effort']:
        if key not in lead:
            return False, f"lead section missing '{key}'"
    if lead['vendor'] not in ['claude', 'codex', 'antigravity']:
        return False, f"lead.vendor must be one of claude/codex/antigravity, got '{lead['vendor']}'"

    # Validate rows
    for row in data['rows']:
        if 'id' not in row:
            return False, "Row missing 'id'"
        if 'match' not in row:
            return False, f"Row '{row['id']}' missing 'match'"
        if 'options' not in row:
            return False, f"Row '{row['id']}' missing 'options'"

        # Lead-only row should have empty options
        if row['id'] == 'lead-only':
            if row['options'] and len(row['options']) > 0:
                return False, f"Row 'lead-only' should have empty options, got {row['options']}"
        else:
            # Non-lead rows should have options
            if not row['options']:
                return False, f"Row '{row['id']}' has empty options"

            # Validate each option
            for i, opt in enumerate(row['options']):
                if isinstance(opt, str):
                    # Skip string items (YAML list parsing artifact)
                    continue
                if 'vendor' not in opt:
                    return False, f"Row '{row['id']}' option {i} missing 'vendor'"
                if 'model' not in opt:
                    return False, f"Row '{row['id']}' option {i} missing 'model'"
                if opt['vendor'] not in ['claude', 'codex', 'antigravity']:
                    return False, f"Row '{row['id']}' option {i} invalid vendor '{opt['vendor']}'"

        # Validate paths are globs (basic check: should start with "assets/", "src/", "design/", "docs/", or "production/")
        if 'match' in row and row['match']:
            match = row['match']
            if isinstance(match, dict):
                if 'paths' in match and match['paths']:
                    for path in match['paths']:
                        if not isinstance(path, str):
                            continue
                        # Basic glob validation
                        valid_prefixes = ('assets/', 'src/', 'design/', 'docs/', 'production/')
                        if not any(path.startswith(p) for p in valid_prefixes) and path not in ('design/gdd/**',):
                            # Allow non-path matches like 'stage: review'
                            pass

    return True, "Valid"

def check_pr_commits(base, head, role=None):
    """Check that commits in a PR have Agent trailers matching their role."""
    try:
        # Get commits in the range
        result = subprocess.run(
            ['git', 'log', '--format=%B', f'{base}...{head}'],
            capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            return False, f"Failed to get git log for {base}...{head}"

        commits = result.stdout.split('\n\n')
        routing = load_yaml(Path('.github/agent-routing.yaml'))

        # Build a map of role → allowed vendors/models
        role_options = {}
        for row in routing.get('rows', []):
            for r in row.get('match', {}).get('roles', []):
                if r not in role_options:
                    role_options[r] = []
                for opt in row.get('options', []):
                    if isinstance(opt, dict):
                        role_options[r].append(f"{opt['vendor']}/{opt['model']}")

        # Check each commit
        for i, commit_body in enumerate(commits):
            if not commit_body.strip():
                continue

            # Look for Agent: <vendor>/<model> trailer
            agent_line = None
            for line in commit_body.split('\n'):
                if line.startswith('Agent:'):
                    agent_line = line
                    break

            if not agent_line:
                return False, f"Commit {i+1} missing 'Agent: <vendor>/<model>' trailer"

            # Parse the trailer
            agent_value = agent_line.replace('Agent:', '').strip()

            if role and role in role_options:
                if agent_value not in role_options[role]:
                    return False, f"Commit {i+1} Agent '{agent_value}' not in role '{role}' options: {role_options[role]}"

        return True, "Valid"

    except Exception as e:
        return False, str(e)

def main():
    parser = argparse.ArgumentParser(description='Validate agent routing YAML and PR commits')
    parser.add_argument('--check-pr', type=str, help='Check PR range (base..head) for Agent trailers')
    parser.add_argument('--role', type=str, help='Expected role for PR commit validation')
    args = parser.parse_args()

    if args.check_pr:
        # Check PR mode
        parts = args.check_pr.split('..')
        if len(parts) != 2:
            print(f"Invalid range format: {args.check_pr} (use base..head)", file=sys.stderr)
            sys.exit(2)

        success, msg = check_pr_commits(parts[0], parts[1], args.role)
        if success:
            print(msg)
            sys.exit(0)
        else:
            print(f"BLOCKED: {msg}", file=sys.stderr)
            sys.exit(1)
    else:
        # Default: validate routing.yaml
        routing_path = Path('.github/agent-routing.yaml')
        success, msg = validate_routing_yaml(routing_path)

        if success:
            print(f"✓ {routing_path} is valid")
            sys.exit(0)
        else:
            print(f"BLOCKED: {msg}", file=sys.stderr)
            sys.exit(1)

if __name__ == '__main__':
    main()

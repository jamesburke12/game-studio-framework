#!/usr/bin/env bash
# PostToolUse hook (Edit|Write) on C# files: report any comment block over the
# 150-word cap in the file just written, so the editing agent condenses it now.
# USER rule 2026-09-05 — see CLAUDE.md "Code comments" and
# tools/code/comment_budget.py. Log the check in production/session-state/comment-budget.md.
input=$(cat)
file=$(printf '%s' "$input" | python -c "import json,sys; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null)
case "$file" in
  *.cs) ;;
  *) exit 0 ;;
esac
cd "$CLAUDE_PROJECT_DIR" || exit 0
out=$(python tools/code/comment_budget.py check "$file" 2>&1)
if [ $? -ne 0 ]; then
  echo "Comment budget: condense these blocks to <=150 words (fewer or none if the code is obvious), then log words removed in production/session-state/comment-budget.md: $out" >&2
  exit 2
fi
exit 0

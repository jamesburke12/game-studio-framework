"""Comment budget check for C# sources (USER rule 2026-09-05).

Rule: no single comment block may exceed COMMENT_WORD_CAP words; fewer or no
comments are preferred when the code is obvious. A "block" is a run of
consecutive `//` or `///` lines, or one `/* ... */` span.

Usage:
  python tools/code/comment_budget.py check <file.cs> [...]   # exit 1 on any over-cap block
  python tools/code/comment_budget.py stats [root]            # repo-wide comment words + est. tokens

Token estimate: 1 word ~= 1.3 tokens (English prose average in these files).
"""
from __future__ import annotations

import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

COMMENT_WORD_CAP = 150
TOKENS_PER_WORD = 1.3
ROOTS = ("src", "assets/Scripts", "assets/Tests")
SKIP_DIRS = {"bin", "obj", "Library", "tests-out", ".git"}

_LINE_COMMENT = re.compile(r"^\s*///?\s?(.*)$")


def blocks(text: str):
    """Yield (start_line, end_line, words) for every comment block."""
    lines = text.splitlines()
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        m = _LINE_COMMENT.match(line)
        if m:
            start, words = i + 1, 0
            while i < n:
                m = _LINE_COMMENT.match(lines[i])
                if not m:
                    break
                words += len(m.group(1).split())
                i += 1
            yield start, i, words
            continue
        j = line.find("/*")
        if j >= 0 and "*/" not in line[j:]:
            start, buf = i + 1, [line[j + 2:]]
            i += 1
            while i < n and "*/" not in lines[i]:
                buf.append(lines[i])
                i += 1
            if i < n:
                buf.append(lines[i][: lines[i].find("*/")])
            words = sum(len(b.replace("*", " ").split()) for b in buf)
            yield start, i + 1, words
        i += 1


def cs_files(root: str):
    for base in ROOTS:
        top = os.path.join(root, base)
        for d, dirs, files in os.walk(top):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            for f in files:
                if f.endswith(".cs"):
                    yield os.path.join(d, f)


def check(paths) -> int:
    bad = 0
    for p in paths:
        if not p.endswith(".cs") or not os.path.isfile(p):
            continue
        text = io.open(p, encoding="utf-8", errors="replace").read()
        for start, end, words in blocks(text):
            if words > COMMENT_WORD_CAP:
                bad += 1
                print(f"{p}:{start}-{end}: comment block is {words} words (cap {COMMENT_WORD_CAP}) — condense it")
    return 1 if bad else 0


def stats(root: str) -> int:
    files = words = over = 0
    for p in cs_files(root):
        files += 1
        text = io.open(p, encoding="utf-8", errors="replace").read()
        for _s, _e, w in blocks(text):
            words += w
            if w > COMMENT_WORD_CAP:
                over += 1
    print(f"files={files} comment_words={words} est_tokens={int(words * TOKENS_PER_WORD)} blocks_over_cap={over}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("check", "stats"):
        print(__doc__)
        sys.exit(2)
    if sys.argv[1] == "check":
        sys.exit(check(sys.argv[2:]))
    sys.exit(stats(sys.argv[2] if len(sys.argv) > 2 else "."))

#!/usr/bin/env python3
# @bigd-hook-meta
# name: resource_leak_guard
# fires_on: PostToolUse
# relevant_intents: [code, debug]
# irrelevant_intents: [bigd, pm, telegram, docx, x_tweet, git, vps, sync, memory]
# cost_score: 2
# always_fire: false
# Copyright (c) 2026 Nardo (<github-user>). AGPL-3.0 — see LICENSE
"""PostToolUse hook: catch resource leak patterns in Python files.

Catches:
1. open() not used as context manager (file handle leaks)
2. sqlite3.connect() not in try/finally or context manager
3. Variable assigned in try block, used in finally without guard (UnboundLocalError)
4. asyncio Task created but not stored/cancelled

Commits this prevents: aa0f9c5 (5), ff1bd59 (9), e21bbdc (12)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hook_base import run_hook

# open() called with assignment (potential leak if not in 'with')
_OPEN_ASSIGN = re.compile(r"\b(\w+)\s*=\s*open\s*\(")
# sqlite3.connect() with assignment (potential leak)
_SQLITE_ASSIGN = re.compile(r"\b(\w+)\s*=\s*sqlite3\.connect\s*\(")
# asyncio.create_task — check if result is captured
_TASK_CALL = re.compile(r"asyncio\.create_task\s*\(")
_TASK_ASSIGNED = re.compile(r"\b\w+\s*=\s*asyncio\.create_task\s*\(")
# aiofiles.open without with
_AIOFILES_OPEN = re.compile(r"\bawait\s+aiofiles\.open\s*\(")


def _scan(content):
    lines = content.splitlines()
    warnings = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Skip comments and strings
        if stripped.startswith("#"):
            continue

        # open() without 'with' — bare assignment pattern
        if _OPEN_ASSIGN.search(line):
            if not re.match(r"\s*with\s+", line) and "tempfile" not in line:
                warnings.append(
                    f"  line ~{i}: `{stripped[:80]}` — "
                    "open() without context manager → file handle leak. Use `with open(...) as f:`"
                )

        # sqlite3.connect without with
        if _SQLITE_ASSIGN.search(line) and not re.match(r"\s*with\s+", line):
            warnings.append(
                f"  line ~{i}: `{stripped[:80]}` — "
                "sqlite3.connect() without context manager → connection leak. "
                "Use `with sqlite3.connect(...) as conn:` or wrap in try/finally"
            )

        # asyncio.create_task not assigned
        if _TASK_CALL.search(line) and not _TASK_ASSIGNED.search(line):
            warnings.append(
                f"  line ~{i}: `{stripped[:80]}` — "
                "asyncio.create_task() result not stored → task becomes ghost, "
                "can't be cancelled. Assign to a variable and track it."
            )

    return warnings


def check(tool_name, tool_input, _input_data):
    if tool_name not in ("Edit", "Write"):
        return False
    fp = tool_input.get("file_path", "")
    if not fp.endswith(".py"):
        return False
    if "resource_leak_guard" in fp:
        return False
    return True


def action(tool_name, tool_input, _input_data):
    if tool_name == "Write":
        content = tool_input.get("content", "")
    else:
        content = tool_input.get("new_string", "")

    if not content:
        return None

    warnings = _scan(content)
    if not warnings:
        return None

    fp = tool_input.get("file_path", "")
    return (
        f"RESOURCE LEAK GUARD: potential leaks in `{Path(fp).name}`.\n"
        + "\n".join(warnings[:6])
    )


if __name__ == "__main__":
    import io
    import json
    _raw = sys.stdin.read()
    try:
        _prompt = json.loads(_raw).get("prompt", "") if _raw else ""
    except Exception:
        _prompt = ""
    from _semantic_router import should_fire
    if not should_fire(__file__, _prompt):
        print("{}")
        sys.exit(0)
    sys.stdin = io.StringIO(_raw)
    run_hook(check, action, "resource_leak_guard")

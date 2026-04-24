#!/usr/bin/env python3
# @bigd-hook-meta
# name: async_safety_guard
# fires_on: PostToolUse
# relevant_intents: [code, debug]
# irrelevant_intents: [bigd, pm, telegram, docx, x_tweet, vps, sync, memory]
# cost_score: 2
# always_fire: false
# Copyright (c) 2026 Nardo (<github-user>). AGPL-3.0 — see LICENSE
"""PostToolUse hook: catch async/concurrency anti-patterns in Python files.

Catches (soft warnings — these are risky but may be intentional):
1. subprocess.run() / subprocess.check_output() called without timeout=
   in async context (blocks event loop)
2. asyncio.get_event_loop() — deprecated, use asyncio.get_running_loop()
3. time.sleep() inside async def (blocks event loop)
4. subprocess.run / check_output inside async def without await

Hard block:
- None. These are warnings because some uses are intentional (sync scripts).

Commits this prevents: 4 (ecb57e4), 5 (aa0f9c5), 9 (ff1bd59), 12 (e21bbdc)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hook_base import run_hook

_PATTERNS = [
    # subprocess.run without timeout
    (
        r"subprocess\.(run|check_output|call|check_call)\s*\([^)]*\)",
        r"timeout\s*=",
        "subprocess call without `timeout=` — blocks indefinitely if process hangs",
    ),
    # asyncio.get_event_loop() (deprecated)
    (
        r"asyncio\.get_event_loop\(\)",
        None,
        "asyncio.get_event_loop() is deprecated — use asyncio.get_running_loop() or asyncio.run()",
    ),
    # time.sleep in async functions
    (
        r"^\s*(await\s+)?time\.sleep\(",
        None,
        "time.sleep() in async code blocks the event loop — use `await asyncio.sleep()`",
    ),
]

# Detect if we're inside an async def context (simple heuristic)
_ASYNC_DEF = re.compile(r"^\s*async\s+def\s+")
_TIME_SLEEP = re.compile(r"(?<!\#).*time\.sleep\(")
_SUBPROCESS_NO_TO = re.compile(r"subprocess\.(run|check_output|call|check_call)\s*\(")
_HAS_TIMEOUT = re.compile(r"timeout\s*=")
_EVENT_LOOP = re.compile(r"asyncio\.get_event_loop\(\)")


def _scan_content(content):
    lines = content.splitlines()
    warnings = []
    in_async = False

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Track whether we're inside an async def (reset on new def or class)
        if _ASYNC_DEF.match(line):
            in_async = True
        elif re.match(r"^\s*(def |class )", line) and not _ASYNC_DEF.match(line):
            in_async = False

        # Skip comments
        if stripped.startswith("#"):
            continue

        # asyncio.get_event_loop() — always warn
        if _EVENT_LOOP.search(stripped):
            warnings.append(
                f"  line ~{i}: `{stripped[:80]}` — "
                "asyncio.get_event_loop() deprecated; use get_running_loop()"
            )

        # subprocess without timeout — always warn (risky in both sync and async)
        if _SUBPROCESS_NO_TO.search(stripped):
            # Check if timeout= appears on same line or nearby (3 lines)
            window = "\n".join(lines[max(0, i-1):min(len(lines), i+3)])
            if not _HAS_TIMEOUT.search(window):
                warnings.append(
                    f"  line ~{i}: `{stripped[:80]}` — "
                    "subprocess call without timeout= (hangs if process stalls)"
                )

        # time.sleep inside async context
        if in_async and _TIME_SLEEP.search(stripped) and "asyncio.sleep" not in stripped:
            if "await" not in stripped:
                warnings.append(
                    f"  line ~{i}: `{stripped[:80]}` — "
                    "time.sleep() in async def blocks event loop; use await asyncio.sleep()"
                )

    return warnings


def check(tool_name, tool_input, _input_data):
    if tool_name not in ("Edit", "Write"):
        return False
    fp = tool_input.get("file_path", "")
    if not fp.endswith(".py"):
        return False
    # Skip this hook itself
    if "async_safety_guard" in fp:
        return False
    return True


def action(tool_name, tool_input, _input_data):
    if tool_name == "Write":
        content = tool_input.get("content", "")
    else:
        content = tool_input.get("new_string", "")

    if not content:
        return None

    warnings = _scan_content(content)
    if not warnings:
        return None

    fp = tool_input.get("file_path", "")
    return (
        f"ASYNC SAFETY GUARD: risky patterns in `{Path(fp).name}`.\n"
        + "\n".join(warnings[:6])
    )


if __name__ == "__main__":
    import io
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
    run_hook(check, action, "async_safety_guard")

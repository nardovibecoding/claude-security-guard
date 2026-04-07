#!/usr/bin/env python3
# Copyright (c) 2026 Nardo. AGPL-3.0 — see LICENSE
"""PostToolUse hook: warn when code writes to /tmp without cleanup.

Catches:
- open("/tmp/...") without tempfile module
- Path("/tmp/...").write without context manager
- Playwright launch without TemporaryDirectory
- Manual os.makedirs("/tmp/...") patterns
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hook_base import run_hook

# Patterns that suggest unmanaged temp files
BAD_PATTERNS = [
    (r'open\(["\']\/tmp\/', "open('/tmp/...') — use tempfile.NamedTemporaryFile"),
    (r'Path\(["\']\/tmp\/', "Path('/tmp/...') — use tempfile module"),
    (r'os\.makedirs\(["\']\/tmp\/', "os.makedirs('/tmp/...') — use tempfile.mkdtemp"),
    (r'["\']\/tmp\/tg_photo', "hardcoded /tmp/tg_photo — use tempfile"),
    (r'["\']\/tmp\/tmp[a-z]', "hardcoded /tmp/tmp* path — use tempfile"),
]

# Safe patterns — skip these
SAFE = [
    r"tempfile\.",
    r"TemporaryDirectory",
    r"NamedTemporaryFile",
    r"mkdtemp",
    r"#.*\/tmp",        # comments
    r"cleanup",         # cleanup code itself is fine
    r"cache_cleanup",   # the cleanup script
    r"glob\.glob.*\/tmp",  # cleanup globs
    r"os\.unlink.*\/tmp",  # cleanup deletes
    r"shutil\.rmtree",    # cleanup rmtree
]


def check(tool_name, tool_input, _input_data):
    if tool_name not in ("Edit", "Write"):
        return False
    fp = tool_input.get("file_path", "")
    if not fp.endswith(".py"):
        return False
    # Don't self-trigger on hook files or cleanup scripts
    if "cache_cleanup" in fp or "temp_file_guard" in fp:
        return False
    return True


def action(tool_name, tool_input, _input_data):
    # Get the new content being written
    if tool_name == "Write":
        content = tool_input.get("content", "")
    else:
        content = tool_input.get("new_string", "")

    if not content:
        return None

    warnings = []
    for line in content.splitlines():
        stripped = line.strip()
        # Skip safe patterns
        if any(re.search(s, stripped) for s in SAFE):
            continue
        for pattern, msg in BAD_PATTERNS:
            if re.search(pattern, stripped):
                warnings.append(
                    f"  `{stripped[:70]}` → {msg}"
                )
                break

    if not warnings:
        return None

    return (
        "⚠️ TEMP FILE GUARD: unmanaged /tmp writes detected.\n"
        "Use `tempfile.NamedTemporaryFile()` or "
        "`tempfile.TemporaryDirectory()` for auto-cleanup.\n"
        + "\n".join(warnings[:5])
    )


if __name__ == "__main__":
    run_hook(check, action, "temp_file_guard")

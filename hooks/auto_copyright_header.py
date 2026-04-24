# Copyright (c) 2026 Nardo (<github-user>). AGPL-3.0 — see LICENSE
#!/usr/bin/env python3
# @bigd-hook-meta
# name: auto_copyright_header
# fires_on: PostToolUse
# relevant_intents: [code, git]
# irrelevant_intents: [bigd, pm, telegram, docx, x_tweet, vps, sync, memory, debug]
# cost_score: 1
# always_fire: false
"""PostToolUse hook: check copyright header after writing .py/.js files."""
import io
import json
import os
import sys
from pathlib import Path


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    if tool_name not in ("Write", "Edit"):
        print("{}")
        return

    file_path = tool_input.get("file_path", "")
    if not file_path:
        print("{}")
        return

    path = Path(file_path)

    # Only check .py and .js files
    if path.suffix not in (".py", ".js"):
        print("{}")
        return

    # Skip non-repo files (hooks dir, tmp, etc.)
    # Only enforce on files under repos that will be published
    skip_dirs = [".claude/hooks", "/tmp/", ".claude/skills"]
    if any(d in file_path for d in skip_dirs):
        print("{}")
        return

    # Check if file has copyright header in first 300 chars
    try:
        head = path.read_text()[:300]
    except Exception:
        print("{}")
        return

    if "Copyright" in head or "SPDX" in head or "license" in head.lower()[:100]:
        print("{}")
        return

    fname = path.name
    print(json.dumps({
        "systemMessage": (
            f"⚠️ **`{fname}` missing copyright header.** Add to top:\n"
            f"`# Copyright (c) 2026 Nardo (<github-user>). AGPL-3.0 — see LICENSE`"
        )
    }))


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(__file__))
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
    main()

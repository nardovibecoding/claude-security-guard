# Copyright (c) 2026 Nardo (<github-user>). AGPL-3.0 — see LICENSE
#!/usr/bin/env python3
"""PostToolUse hook: check copyright header after writing .py/.js files."""
import json
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
    main()

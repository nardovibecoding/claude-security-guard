#!/usr/bin/env python3
"""PostToolUse hook: validate Python syntax after git commit on telegram-claude-bot."""
import json
import re
import subprocess
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

    if tool_name != "Bash":
        print("{}")
        return

    cmd = tool_input.get("command", "")
    if not re.search(r"git\s+commit", cmd):
        print("{}")
        return

    # Only check telegram-claude-bot repo
    cwd = input_data.get("cwd", "")
    if "telegram-claude-bot" not in cwd:
        print("{}")
        return

    # Get changed files from last commit
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "diff", "--name-only", "HEAD~1", "HEAD"],
            capture_output=True, text=True, timeout=10
        )
        changed = [f for f in result.stdout.strip().splitlines() if f.endswith(".py")]
    except Exception:
        print("{}")
        return

    if not changed:
        print("{}")
        return

    # Validate syntax
    errors = []
    for f in changed:
        full_path = Path(cwd) / f
        if not full_path.exists():
            continue
        try:
            result = subprocess.run(
                ["python3", "-m", "py_compile", str(full_path)],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                errors.append(f"{f}: {result.stderr.strip()[:100]}")
        except Exception:
            pass

    if errors:
        msg = "⚠️ **Syntax errors in committed files:**\n"
        msg += "\n".join(f"  - {e}" for e in errors[:5])
        msg += "\nFix before pushing."
        print(json.dumps({"systemMessage": msg}))
    else:
        print("{}")


if __name__ == "__main__":
    main()

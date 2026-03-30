#!/usr/bin/env python3
# Copyright (c) 2026 Nardo (nardovibecoding). AGPL-3.0 — see LICENSE
"""Stop hook: auto-commit changed memory files when session ends."""
import json
import subprocess
import sys
from pathlib import Path

MEMORY_DIR = Path.home() / ".claude" / "projects" / f"-Users-{Path.home().name}" / "memory"


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return

    if not MEMORY_DIR.exists():
        print("{}")
        return

    # Check for uncommitted memory changes
    try:
        result = subprocess.run(
            ["git", "-C", str(MEMORY_DIR.parent.parent.parent), "diff", "--name-only", "memory/"],
            capture_output=True, text=True, timeout=5, cwd=str(MEMORY_DIR.parent)
        )
        changed = result.stdout.strip()

        # Also check untracked
        result2 = subprocess.run(
            ["git", "-C", str(MEMORY_DIR.parent.parent.parent), "ls-files", "--others",
             "--exclude-standard", "memory/"],
            capture_output=True, text=True, timeout=5, cwd=str(MEMORY_DIR.parent)
        )
        untracked = result2.stdout.strip()
    except Exception:
        print("{}")
        return

    files = []
    if changed:
        files.extend(changed.splitlines())
    if untracked:
        files.extend(untracked.splitlines())

    if not files:
        print("{}")
        return

    msg = f"📋 **{len(files)} memory file(s) uncommitted:**\n"
    msg += "\n".join(f"  - {f}" for f in files[:10])
    msg += "\nCommit these before ending the session."
    print(json.dumps({"systemMessage": msg}))


if __name__ == "__main__":
    main()

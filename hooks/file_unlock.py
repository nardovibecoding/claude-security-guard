#!/usr/bin/env python3
"""PostToolUse hook: release file lock after Edit/Write completes."""
import json
import os
import sys
from hashlib import md5
from pathlib import Path

LOCK_DIR = Path("/tmp/claude_file_locks")


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    if tool_name not in ("Edit", "Write"):
        print("{}")
        return

    file_path = tool_input.get("file_path", "")
    if not file_path:
        print("{}")
        return

    lock_key = md5(file_path.encode()).hexdigest()[:12]
    lock_file = LOCK_DIR / f"{lock_key}.lock"

    # Only release if we own the lock
    if lock_file.exists():
        try:
            content = lock_file.read_text().strip()
            locked_pid = int(content.split("|")[0])
            if locked_pid == os.getpid():
                lock_file.unlink()
        except (ValueError, IndexError, OSError):
            pass

    print("{}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""PreToolUse hook: file lock — prevents two agents from editing the same file simultaneously.

Uses /tmp/claude_file_locks/ directory. Each lock file contains the PID + timestamp.
Lock expires after 60 seconds (stale agent detection).
"""
import json
import os
import sys
import time
from hashlib import md5
from pathlib import Path

LOCK_DIR = Path("/tmp/claude_file_locks")
LOCK_EXPIRE_SECONDS = 60


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # Only check Edit and Write
    if tool_name not in ("Edit", "Write"):
        print("{}")
        return

    file_path = tool_input.get("file_path", "")
    if not file_path:
        print("{}")
        return

    LOCK_DIR.mkdir(exist_ok=True)

    # Create a lock key from the file path
    lock_key = md5(file_path.encode()).hexdigest()[:12]
    lock_file = LOCK_DIR / f"{lock_key}.lock"

    my_pid = os.getpid()
    now = time.time()

    # Check if lock exists
    if lock_file.exists():
        try:
            content = lock_file.read_text().strip()
            parts = content.split("|")
            locked_pid = int(parts[0])
            locked_time = float(parts[1])
            locked_path = parts[2] if len(parts) > 2 else "unknown"

            # Check if lock is stale (expired or dead process)
            is_stale = (now - locked_time) > LOCK_EXPIRE_SECONDS
            is_dead = False
            try:
                os.kill(locked_pid, 0)  # Check if process alive
            except OSError:
                is_dead = True

            if not is_stale and not is_dead and locked_pid != my_pid:
                fname = Path(file_path).name
                print(json.dumps({
                    "systemMessage": (
                        f"⚠️ **File lock: `{fname}` is being edited by another agent** (PID {locked_pid}, "
                        f"{int(now - locked_time)}s ago). Wait for it to finish or the lock expires in "
                        f"{int(LOCK_EXPIRE_SECONDS - (now - locked_time))}s."
                    )
                }))
                return

        except (ValueError, IndexError):
            pass  # Corrupt lock file, overwrite it

    # Acquire lock
    lock_file.write_text(f"{my_pid}|{now}|{file_path}")

    print("{}")


if __name__ == "__main__":
    main()

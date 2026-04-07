#!/usr/bin/env python3
"""Stop hook: exit session when /convos writes exit_pending marker.

Writes relaunch marker, cleans up, SIGTERMs claude immediately.
Other parallel hooks bail instantly on exit_pending — no delay needed.
"""
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

EXIT_PENDING_GLOBAL = Path("/tmp/claude_ctx_exit_pending")


def get_exit_pending_path():
    tty_id = os.environ.get("CLAUDE_TTY_ID", "").strip()
    if tty_id:
        return Path(f"/tmp/claude_ctx_exit_pending_{tty_id}")
    return EXIT_PENDING_GLOBAL


def main():
    try:
        json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        pass

    exit_file = get_exit_pending_path()
    if not exit_file.exists() and not EXIT_PENDING_GLOBAL.exists():
        print("{}")
        return

    tty_id = os.environ.get("CLAUDE_TTY_ID", "").strip()
    if tty_id:
        Path(f"/tmp/claude_auto_relaunch_{tty_id}").write_text("1")
    else:
        Path("/tmp/claude_auto_relaunch").write_text("1")

    exit_file.unlink(missing_ok=True)
    EXIT_PENDING_GLOBAL.unlink(missing_ok=True)

    # Find and kill claude process — other hooks already bailed on exit_pending
    pid = os.getppid()
    for _ in range(10):
        if pid <= 1:
            break
        try:
            ps_out = subprocess.check_output(
                ["ps", "-p", str(pid), "-o", "args="], text=True
            ).strip()
        except subprocess.CalledProcessError:
            break
        if "claude" in ps_out.lower():
            os.kill(pid, signal.SIGTERM)
            return
        try:
            pid = int(subprocess.check_output(
                ["ps", "-p", str(pid), "-o", "ppid="], text=True
            ).strip())
        except (subprocess.CalledProcessError, ValueError):
            break

    print(json.dumps({"continue": False}), flush=True)


if __name__ == "__main__":
    main()

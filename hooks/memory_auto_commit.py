#!/usr/bin/env python3
# Copyright (c) 2026 Nardo (nardovibecoding). AGPL-3.0 — see LICENSE
"""Stop hook: auto-sync and commit changed memory files when session ends."""
import json
import os
import subprocess
import sys
from pathlib import Path

# Skip during convos (auto-clear flow)
_tty = os.environ.get("CLAUDE_TTY_ID", "").strip()
if Path(f"/tmp/claude_ctx_exit_pending_{_tty}").exists() if _tty else Path("/tmp/claude_ctx_exit_pending").exists():
    print("{}")
    sys.exit(0)

MEMORY_SRC = Path.home() / ".claude" / "projects" / f"-Users-{Path.home().name}" / "memory"
BOT_REPO = Path.home() / "telegram-claude-bot"
MEMORY_DST = BOT_REPO / "memory"


def run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=15, **kwargs)


def main():
    try:
        json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        pass

    if not MEMORY_SRC.exists() or not BOT_REPO.exists():
        print("{}")
        return

    # Rsync memory from ~/.claude/ to telegram-claude-bot/memory/
    run(["rsync", "-a", "--delete",
         str(MEMORY_SRC) + "/",
         str(MEMORY_DST) + "/"])

    # Check for changes in bot repo memory/
    diff = run(["git", "status", "--porcelain", "memory/"], cwd=BOT_REPO)
    changed_lines = [l for l in diff.stdout.strip().splitlines() if l.strip()]

    if not changed_lines:
        print("{}")
        return

    # Count files
    n = len(changed_lines)

    # Auto-commit
    run(["git", "add", "memory/"], cwd=BOT_REPO)
    run(["git", "commit", "-m", f"memory: auto-sync {n} file(s) at session end"],
        cwd=BOT_REPO)

    print(json.dumps({"systemMessage": f"Memory auto-committed: {n} file(s) synced to telegram-claude-bot."}))


if __name__ == "__main__":
    main()

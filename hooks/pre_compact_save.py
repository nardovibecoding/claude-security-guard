#!/usr/bin/env python3
"""PreCompact hook: save transcript + remind to /s before compaction."""
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

SESSION_LOG_DIR = Path.home() / ".claude" / "session-logs"
MAX_LOGS = 30


def main():
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        hook_input = {}

    transcript_path = hook_input.get("transcript_path", "")

    # Save transcript backup
    if transcript_path and os.path.exists(transcript_path):
        SESSION_LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = SESSION_LOG_DIR / f"session_{ts}.jsonl"
        try:
            shutil.copy2(transcript_path, dest)
        except Exception:
            pass

        # Prune old logs, keep MAX_LOGS most recent
        logs = sorted(SESSION_LOG_DIR.glob("session_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in logs[MAX_LOGS:]:
            old.unlink(missing_ok=True)

    # Remind to save memory before compaction wipes context
    print(json.dumps({
        "systemMessage": (
            "COMPACTION IMMINENT. Run /s now (Skill tool, skill='s') to save "
            "conversation memory before context is compressed. Do not ask, just do it."
        )
    }))


if __name__ == "__main__":
    main()
